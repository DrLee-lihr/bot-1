import asyncio
import datetime
import re
import traceback
import urllib.parse
from typing import Union, Dict, List

import ujson as json

import core.html2text as html2text
from core.dirty_check import check
from core.elements import Url
from core.logger import Logger
from core.utils import get_url
from .dbutils import WikiSiteInfo as DBSiteInfo, Audit


class InvalidPageIDError(Exception):
    pass


class InvalidWikiError(Exception):
    pass


class DangerousContentError(Exception):
    pass


class PageNotFound(Exception):
    pass


class WhatAreUDoingError(Exception):
    pass


class QueryInfo:
    def __init__(self, api, headers=None, prefix=None):
        self.api = api
        self.headers = headers if headers is not None else {
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'}
        self.prefix = prefix


class WikiInfo:
    def __init__(self,
                 api: str = '',
                 articlepath: str = '',
                 extensions=None,
                 interwiki=None,
                 realurl: str = '',
                 name: str = '',
                 namespaces=None,
                 namespaces_local=None,
                 in_allowlist=False,
                 in_blocklist=False,
                 script: str = '',
                 logo_url: str = ''):
        if extensions is None:
            extensions = []
        if interwiki is None:
            interwiki = {}
        self.api = api
        self.articlepath = articlepath
        self.extensions = extensions
        self.interwiki = interwiki
        self.realurl = realurl
        self.name = name
        self.namespaces = namespaces
        self.namespaces_local = namespaces_local
        self.in_allowlist = in_allowlist
        self.in_blocklist = in_blocklist
        self.script = script
        self.logo_url = logo_url


class WikiStatus:
    def __init__(self,
                 available: bool,
                 value: Union[WikiInfo, bool],
                 message: str):
        self.available = available
        self.value = value
        self.message = message


class PageInfo:
    def __init__(self,
                 info: WikiInfo,
                 title: str,
                 id: int = -1,
                 before_title: str = None,
                 link: str = None,
                 file: str = None,
                 desc: str = None,
                 args: str = None,
                 section: str = None,
                 interwiki_prefix: str = '',
                 status: bool = True,
                 before_page_property: str = 'page',
                 page_property: str = 'page',
                 invalid_namespace: bool = False
                 ):
        self.info = info
        self.id = id
        self.title = title
        self.before_title = before_title
        self.link = link
        self.file = file
        self.desc = desc
        self.args = args
        self.section = section
        self.interwiki_prefix = interwiki_prefix
        self.status = status
        self.before_page_property = before_page_property
        self.page_property = page_property
        self.invalid_namespace = invalid_namespace


class WikiLib:
    def __init__(self, url: str, headers=None):
        self.url = url
        self.wiki_info = WikiInfo()
        self.headers = headers

    async def get_json_from_api(self, api, log=False, **kwargs) -> dict:
        if kwargs is not None:
            api = api + '?' + urllib.parse.urlencode(kwargs) + '&format=json'
            Logger.info(api)
        else:
            raise ValueError('kwargs is None')
        return await get_url(api, status_code=200, headers=self.headers, fmt="json", log=log)

    def rearrange_siteinfo(self, info: Union[dict, str], wiki_api_link) -> WikiInfo:
        if isinstance(info, str):
            info = json.loads(info)
        extensions = info['query']['extensions']
        ext_list = []
        for ext in extensions:
            ext_list.append(ext['name'])
        real_url = info['query']['general']['server']
        if real_url.startswith('//'):
            real_url = self.url.split('//')[0] + real_url
        namespaces = []
        namespaces_local = {}
        for x in info['query']['namespaces']:
            try:
                ns = info['query']['namespaces'][x]
                if '*' in ns:
                    namespaces.append(ns['*'])
                if 'canonical' in ns:
                    namespaces.append(ns['canonical'])
                if '*' in ns and 'canonical' in ns:
                    namespaces_local.update({ns['*']: ns['canonical']})
            except Exception:
                traceback.print_exc()
        for x in info['query']['namespacealiases']:
            if '*' in x:
                namespaces.append(x['*'])
        interwiki_map = info['query']['interwikimap']
        interwiki_dict = {}
        for interwiki in interwiki_map:
            interwiki_dict[interwiki['prefix']] = interwiki['url']
        api_url = wiki_api_link
        audit = Audit(api_url)
        return WikiInfo(articlepath=real_url + info['query']['general']['articlepath'],
                        extensions=ext_list,
                        name=info['query']['general']['sitename'],
                        realurl=real_url,
                        api=api_url,
                        namespaces=namespaces,
                        namespaces_local=namespaces_local,
                        interwiki=interwiki_dict,
                        in_allowlist=audit.inAllowList,
                        in_blocklist=audit.inBlockList,
                        script=real_url + info['query']['general']['script'],
                        logo_url=info['query']['general'].get('logo'))

    async def check_wiki_available(self):
        try:
            api_match = re.match(r'(https?://.*?/api.php$)', self.url)
            wiki_api_link = api_match.group(1)
        except Exception:
            try:
                get_page = await get_url(self.url, fmt='text', headers=self.headers)
                if get_page.find('<title>Attention Required! | Cloudflare</title>') != -1:
                    return WikiStatus(available=False, value=False, message='CloudFlare拦截了机器人的请求，请联系站点管理员解决此问题。')
                m = re.findall(
                    r'(?im)<\s*link\s*rel="EditURI"\s*type="application/rsd\+xml"\s*href="([^>]+?)\?action=rsd"\s*/\s*>',
                    get_page)
                api_match = m[0]
                if api_match.startswith('//'):
                    api_match = self.url.split('//')[0] + api_match
                # Logger.info(api_match)
                wiki_api_link = api_match
            except (TimeoutError, asyncio.TimeoutError):
                return WikiStatus(available=False, value=False, message='错误：尝试建立连接超时。')
            except Exception as e:
                traceback.print_exc()
                if e.args == (403,):
                    message = '服务器拒绝了机器人的请求。'
                elif not re.match(r'^(https?://).*', self.url):
                    message = '所给的链接没有指明协议头（链接应以http://或https://开头）。'
                else:
                    message = '此站点也许不是一个有效的Mediawiki：' + str(e)
                if self.url.find('moegirl.org.cn') != -1:
                    message += '\n萌娘百科的api接口不稳定，请稍后再试或直接访问站点。'
                return WikiStatus(available=False, value=False, message=message)
        get_cache_info = DBSiteInfo(wiki_api_link).get()
        if get_cache_info and datetime.datetime.now().timestamp() - get_cache_info[1].timestamp() < 43200:
            return WikiStatus(available=True,
                              value=self.rearrange_siteinfo(get_cache_info[0], wiki_api_link),
                              message='')
        try:
            get_json = await self.get_json_from_api(wiki_api_link, log=True,
                                                    action='query',
                                                    meta='siteinfo',
                                                    siprop='general|namespaces|namespacealiases|interwikimap|extensions')
        except Exception as e:
            traceback.print_exc()
            message = '从API获取信息时出错：' + str(e)
            if self.url.find('moegirl.org.cn') != -1:
                message += '\n萌娘百科的api接口不稳定，请稍后再试或直接访问站点。'
            return WikiStatus(available=False, value=False, message=message)
        DBSiteInfo(wiki_api_link).update(get_json)
        info = self.rearrange_siteinfo(get_json, wiki_api_link)
        return WikiStatus(available=True, value=info,
                          message='警告：此wiki没有启用TextExtracts扩展，返回的页面预览内容将为未处理的原始Wikitext文本。'
                          if 'TextExtracts' not in info.extensions else '')

    async def fixup_wiki_info(self):
        if self.wiki_info.api == '':
            wiki_info = await self.check_wiki_available()
            if wiki_info.available:
                self.wiki_info = wiki_info.value
            else:
                raise InvalidWikiError(wiki_info.message if wiki_info.message != '' else '')

    async def get_json(self, **kwargs) -> dict:
        await self.fixup_wiki_info()
        api = self.wiki_info.api
        return await self.get_json_from_api(api, **kwargs)

    @staticmethod
    def parse_text(text):
        try:
            desc = text.split('\n')
            desc_list = []
            for x in desc:
                if x != '':
                    desc_list.append(x)
            desc = '\n'.join(desc_list)
            desc_end = re.findall(r'(.*?(?:!\s|\?\s|\.\s|！|？|。)).*', desc, re.S | re.M)
            if desc_end:
                if re.findall(r'[({\[>\"\'《【‘“「（]', desc_end[0]):
                    desc_end = re.findall(r'(.*?[)}\]>\"\'》】’”」）].*?(?:!\s|\?\s|\.\s|！|？|。)).*', desc, re.S | re.M)
                desc = desc_end[0]
        except Exception:
            traceback.print_exc()
            desc = ''
        if desc in ['...', '…']:
            desc = ''
        ell = False
        if len(desc) > 250:
            desc = desc[0:250]
            ell = True
        split_desc = desc.split('\n')
        for d in split_desc:
            if d == '':
                split_desc.remove('')
        if len(split_desc) > 5:
            split_desc = split_desc[0:5]
            ell = True
        return '\n'.join(split_desc) + ('...' if ell else '')

    async def get_html_to_text(self, page_name, section=None):
        await self.fixup_wiki_info()
        get_parse = await self.get_json(action='parse',
                                        page=page_name,
                                        prop='text')
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_tables = True
        h.single_line_break = True
        t = h.handle(get_parse['parse']['text']['*'])
        if section is not None:
            s = re.split(r'(.*##[^#].*\[.*?])', t, re.M | re.S)
            ls = len(s)
            if ls > 1:
                i = 0
                for x in s:
                    i += 1
                    if re.match(r'##[^#]' + section + r'\[.*?]', x):
                        break
                if i != ls:
                    t = ''.join(s[i:])
        return t

    async def get_wikitext(self, page_name):
        await self.fixup_wiki_info()
        try:
            load_desc = await self.get_json(action='parse',
                                            page=page_name,
                                            prop='wikitext')
            desc = load_desc['parse']['wikitext']['*']
        except Exception:
            traceback.print_exc()
            desc = ''
        return desc

    async def research_page(self, page_name: str):
        await self.fixup_wiki_info()
        get_page = await self.get_json(action='query',
                                       list='search',
                                       srsearch=page_name,
                                       srwhat='text',
                                       srlimit='1',
                                       srenablerewrites=True)
        new_page_name = get_page['query']['search'][0]['title'] if len(get_page['query']['search']) > 0 else None
        title_split = page_name.split(':')
        print(title_split, len(title_split))
        is_invalid_namespace = False
        if len(title_split) > 1 and title_split[0] not in self.wiki_info.namespaces:
            is_invalid_namespace = True
        return new_page_name, is_invalid_namespace

    async def parse_page_info(self, title: str = None, pageid: int = None, doc_mode=False,
                              tried_iw=0, iw_prefix='', iw_mode=False) -> PageInfo:
        """
        :param title: 页面标题，如果为None，则使用pageid
        :param pageid: 页面id
        :param doc_mode: 是否为文档模式
        :param tried_iw: 尝试iw跳转的次数
        :param iw_prefix: iw前缀
        :param iw_mode: 是否为iw模式
        :return:
        """
        try:
            await self.fixup_wiki_info()
        except InvalidWikiError as e:
            link = None
            if self.url.find('$1') != -1:
                link = self.url.replace('$1', title)
            return PageInfo(title=title if title is not None else pageid, id=pageid,
                            link=link, desc='发生错误：' + str(e), info=self.wiki_info)
        ban = False
        if self.wiki_info.in_blocklist and not self.wiki_info.in_allowlist:
            ban = True
        if tried_iw > 5:
            raise WhatAreUDoingError
        section = None
        if title is not None:
            if title == '':
                return PageInfo(title='', link=self.wiki_info.articlepath.replace("$1", ""), info=self.wiki_info)
            split_name = re.split(r'([#?])', title)
            title = re.sub('_', ' ', split_name[0])
            arg_list = []
            section_list = []
            quote_code = False
            for a in split_name[1:]:
                if a[0] == '#':
                    quote_code = True
                if a[0] == '?':
                    quote_code = False
                if quote_code:
                    arg_list.append(urllib.parse.quote(a))
                    section_list.append(a)
                else:
                    arg_list.append(a)
            if len(section_list) > 1:
                section = ''.join(section_list)[1:]
            page_info = PageInfo(info=self.wiki_info, title=title, args=''.join(arg_list), interwiki_prefix=iw_prefix)
            page_info.section = section
            query_string = {'action': 'query', 'prop': 'info|imageinfo', 'inprop': 'url', 'iiprop': 'url',
                            'redirects': 'True', 'titles': title}
        elif pageid is not None:
            page_info = PageInfo(info=self.wiki_info, title=title, args='', interwiki_prefix=iw_prefix)
            query_string = {'action': 'query', 'prop': 'info|imageinfo', 'inprop': 'url', 'iiprop': 'url',
                            'redirects': 'True', 'pageids': pageid}
        else:
            raise ValueError('title and pageid cannot be both None')
        use_textextracts = True if 'TextExtracts' in self.wiki_info.extensions else False
        if use_textextracts and section is None:
            query_string.update({'prop': 'info|imageinfo|extracts|pageprops',
                                 'ppprop': 'description|displaytitle|disambiguation|infoboxes', 'explaintext': 'true',
                                 'exsectionformat': 'plain', 'exchars': '200'})
        get_page = await self.get_json(**query_string)
        query = get_page.get('query')
        print(query)
        if query is None:
            return PageInfo(title=title, link=None, desc='发生错误：API未返回任何内容，请联系此站点管理员获取原因。',
                            info=self.wiki_info)
        redirects_: List[Dict[str, str]] = query.get('redirects')
        if redirects_ is not None:
            for r in redirects_:
                if r['from'] == title:
                    page_info.before_title = r['from']
                    page_info.title = r['to']
        normalized_: List[Dict[str, str]] = query.get('normalized')
        if normalized_ is not None:
            for n in normalized_:
                if n['from'] == title:
                    page_info.before_title = n['from']
                    page_info.title = n['to']
        pages: Dict[str, dict] = query.get('pages')
        print(pages)
        if pages is not None:
            for page_id in pages:
                page_info.id = int(page_id)
                page_raw = pages[page_id]
                if 'missing' in page_raw:
                    if 'title' in page_raw:
                        if 'invalid' in page_raw:
                            rs1 = re.sub('The requested page title contains invalid characters:', '请求的页面标题包含非法字符：',
                                         page_raw['invalidreason'])
                            rs = '发生错误：“' + rs1 + '”。'
                            rs = re.sub('".”', '"”', rs)
                            page_info.desc = rs
                            page_info.status = False
                        elif 'known' in page_raw:
                            full_url = re.sub(r'\$1', urllib.parse.quote(title.encode('UTF-8')),
                                              self.wiki_info.articlepath) \
                                       + page_info.args
                            page_info.link = full_url
                            file = None
                            if 'imageinfo' in page_raw:
                                file = page_raw['imageinfo'][0]['url']
                            page_info.file = file
                            page_info.status = True
                        else:
                            split_title = title.split(':')
                            if len(split_title) > 1 and split_title[0] in self.wiki_info.namespaces_local \
                                and self.wiki_info.namespaces_local[split_title[0]] == 'Template':
                                rstitle = ':'.join(split_title[1:]) + page_info.args
                                research = await self.parse_page_info(rstitle)
                                page_info.title = research.title
                                page_info.link = research.link
                                page_info.desc = research.desc
                                page_info.file = research.file
                                page_info.before_title = title
                                page_info.before_page_property = 'template'
                                page_info.status = research.status
                            else:
                                research = await self.research_page(title)
                                page_info.title = research[0]
                                page_info.before_title = title
                                page_info.invalid_namespace = research[1]
                                page_info.status = False
                    else:
                        page_info.status = False
                else:
                    if 'special' in page_raw:
                        full_url = re.sub(r'\$1', urllib.parse.quote(title.encode('UTF-8')), self.wiki_info.articlepath) \
                                   + page_info.args
                        page_info.link = full_url
                        page_info.status = True
                    else:
                        title = page_raw['title']
                        page_desc = ''
                        split_title = title.split(':')
                        get_desc = True
                        if not doc_mode and len(split_title) > 1 and split_title[0] in self.wiki_info.namespaces_local \
                            and self.wiki_info.namespaces_local[split_title[0]] == 'Template':
                            get_all_text = await self.get_wikitext(title)
                            match_doc = re.match(r'.*{{documentation\|?(.*?)}}.*', get_all_text, re.I | re.S)
                            if match_doc:
                                match_link = re.match(r'link=(.*)', match_doc.group(1), re.I | re.S)
                                if match_link:
                                    get_doc = match_link.group(1)
                                else:
                                    get_doc = title + '/doc'
                                get_desc = False
                                get_doc_desc = await self.parse_page_info(get_doc, doc_mode=True)
                                page_desc = get_doc_desc.desc
                                page_info.before_page_property = page_info.page_property = 'template'
                        if get_desc:
                            if use_textextracts and section is None:
                                raw_desc = page_raw.get('extract')
                                if raw_desc is not None:
                                    page_desc = self.parse_text(raw_desc)
                            else:
                                page_desc = self.parse_text(await self.get_html_to_text(title, section))
                        full_url = page_raw['fullurl'] + page_info.args
                        file = None
                        if 'imageinfo' in page_raw:
                            file = page_raw['imageinfo'][0]['url']
                        page_info.title = title
                        page_info.link = full_url
                        page_info.file = file
                        page_info.desc = page_desc
                        if not iw_mode and page_info.args == '':
                            page_info.link = self.wiki_info.script + f'?curid={page_info.id}'
        interwiki_: List[Dict[str, str]] = query.get('interwiki')
        if interwiki_ is not None:
            for i in interwiki_:
                if i['title'] == page_info.title:
                    iw_title = re.match(r'^' + i['iw'] + ':(.*)', i['title'])
                    iw_title = iw_title.group(1)
                    iw_prefix += i['iw'] + ':'
                    iw_mode = True
                    iw_query = await WikiLib(url=self.wiki_info.interwiki[i['iw']]).parse_page_info(iw_title,
                                                                                                    tried_iw=tried_iw + 1,
                                                                                                    iw_prefix=iw_prefix,
                                                                                                    iw_mode=iw_mode)
                    before_page_info = page_info
                    page_info = iw_query
                    if iw_query.title == '':
                        page_info.title = title
                    else:
                        page_info.before_title = before_page_info.title
                        t = page_info.title
                        if t is not None:
                            if before_page_info.args is not None:
                                page_info.before_title += urllib.parse.unquote(before_page_info.args)
                                t += urllib.parse.unquote(before_page_info.args)
                                if page_info.link is not None:
                                    page_info.link += before_page_info.args
                            else:
                                page_info.link = self.wiki_info.script + f'?curid={page_info.id}'
                            if tried_iw == 0:
                                page_info.title = page_info.interwiki_prefix + t
                                if before_page_info.section is not None:
                                    page_info.section = before_page_info.section
        if not self.wiki_info.in_allowlist:
            checklist = []
            if page_info.title is not None:
                checklist.append(page_info.title)
            if page_info.before_title is not None:
                checklist.append(page_info.before_title)
            if page_info.desc is not None:
                checklist.append(page_info.desc)
            chk = await check(*checklist)
            for x in chk:
                if not x['status']:
                    ban = True
        if ban:
            page_info.status = False
            page_info.title = page_info.before_title = None
            page_info.id = -1
            page_info.desc = str(Url(page_info.link, use_mm=True))
            page_info.link = None
        return page_info

    async def random_page(self) -> PageInfo:
        """
        获取随机页面
        :return: 页面信息
        """
        await self.fixup_wiki_info()
        random_url = await self.get_json(action='query', list='random')
        page_title = random_url['query']['random'][0]['title']
        return await self.parse_page_info(page_title)
