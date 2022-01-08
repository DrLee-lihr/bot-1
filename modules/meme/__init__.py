from core.component import on_command
from core.elements import MessageSession
from core.dirty_check import check
from core.logger import Logger
from modules.meme.jiki import jiki
from modules.meme.moegirl import moegirl
from modules.meme.nbnhhsh import nbnhhsh
from modules.meme.urban import urban

meme = on_command(
    bind_prefix='meme',
    desc='全功能梗查询。',
    developers=['Dianliang233'])


@meme.handle(help_doc='<term> {在小鸡词典、萌娘百科、nbnhhsh、Urban Dictionary 中查询梗}')
async def _(msg: MessageSession):
    res_jiki = await jiki(msg.parsed_msg['<term>'])
    res_moegirl = await moegirl(msg.parsed_msg['<term>'])
    res_nbnhhsh = await nbnhhsh(msg.parsed_msg['<term>'])
    res_urban = await urban(msg.parsed_msg['<term>'])
    chk = await check(res_jiki, res_moegirl, res_nbnhhsh, res_urban)
    res = ''
    for i in chk:
        if not i['status']:
            i = '[???] <REDACTED>'
            res += i + '\n'
        else:
            res += i['content'] + '\n'
    Logger.info('res:'+res)
    await msg.sendMessage(res)
