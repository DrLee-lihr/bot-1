import re
from collections import defaultdict

from core.component import on_command, on_regex
from core.elements import Plain, Image as BImage, MessageSession
from modules.maimai.libraries.image import *
from modules.maimai.libraries.maimai_best_40 import generate
from modules.maimai.libraries.maimaidx_music import *
from modules.maimai.libraries.tool import hash


def song_txt(music: Music):
    return [Plain(f"{music.id}. {music.title}\n"),
            BImage(f"https://www.diving-fish.com/covers/{music.id}.jpg", ),
            Plain(f"\n{'/'.join(music.level)}")]


def inner_level_q(ds1, ds2=None):
    result_set = []
    diff_label = ['Bas', 'Adv', 'Exp', 'Mst', 'ReM']
    if ds2 is not None:
        music_data = total_list.filter(ds=(ds1, ds2))
    else:
        music_data = total_list.filter(ds=ds1)
    for music in sorted(music_data, key=lambda i: int(i['id'])):
        for i in music.diff:
            result_set.append((music['id'], music['title'], music['ds'][i], diff_label[i], music['level'][i]))
    return result_set


innlevel = on_command('maimai_inner_level', alias=['定数查歌'], developers=['mai-bot', 'OasisAkari'])


@innlevel.handle(['~maimai_inner_level <定数>',
                  '~maimai_inner_level <定数下限> <定数上限>'])
async def _(msg: MessageSession):
    if msg.parsed_msg['<定数>'] is not None:
        result_set = inner_level_q(float(msg.parsed_msg['<定数>']))
    else:
        result_set = inner_level_q(float(msg.parsed_msg['<定数下限>']), float(msg.parsed_msg['<定数下限>']))
    if len(result_set) > 50:
        return await msg.sendMessage(f"结果过多（{len(result_set)} 条），请缩小搜索范围。")
    s = ""
    for elem in result_set:
        s += f"{elem[0]}. {elem[1]} {elem[3]} {elem[4]}({elem[2]})\n"
    await msg.sendMessage(s.strip())


mrgex1 = on_regex('maimai_random_music_regex1',
                  desc='随个[dx/标准][绿黄红紫白]<难度> 随机一首指定条件的乐曲', developers=['mai-bot', 'OasisAkari'])


@mrgex1.handle(r"随个((?:dx|sd|标准))?([绿黄红紫白]?)([0-9]+\+?)")
async def _(msg: MessageSession):
    res = msg.matched_msg
    if res:
        try:
            if res.groups()[0] == "dx":
                tp = ["DX"]
            elif res.groups()[0] == "sd" or res.groups()[0] == "标准":
                tp = ["SD"]
            else:
                tp = ["SD", "DX"]
            level = res.groups()[2]
            if res.groups()[1] == "":
                music_data = total_list.filter(level=level, type=tp)
            else:
                music_data = total_list.filter(level=level, diff=['绿黄红紫白'.index(res.groups()[1])], type=tp)
            if len(music_data) == 0:
                rand_result = "没有这样的乐曲哦。"
            else:
                rand_result = song_txt(music_data.random())
            await msg.sendMessage(rand_result)
        except Exception as e:
            print(e)
            await msg.sendMessage("随机命令错误，请检查语法")


mrgex2 = on_regex('maimai_random_music_regex2', desc='XXXmaimaiXXX什么 随机一首歌', developers=['mai-bot', 'OasisAkari'])


@mrgex2.handle(r".*maimai.*什么", )
async def _(msg: MessageSession):
    await msg.sendMessage(song_txt(total_list.random()))


msrgex = on_regex('maimai_search_music_regex', desc='查歌<乐曲标题的一部分> 查询符合条件的乐曲', developers=['mai-bot', 'OasisAkari'])


@msrgex.handle(r"查歌(.+)")
async def _(msg: MessageSession):
    name = msg.matched_msg.groups()[0].strip()
    if name == "":
        return
    res = total_list.filter(title_search=name)
    if len(res) == 0:
        await msg.sendMessage("没有找到这样的乐曲。")
    elif len(res) < 50:
        search_result = ""
        for music in sorted(res, key=lambda i: int(i['id'])):
            search_result += f"{music['id']}. {music['title']}\n"
        return await msg.sendMessage([Plain(search_result.strip())])
    else:
        await msg.sendMessage(f"结果过多（{len(res)} 条），请缩小查询范围。")


mqrgex = on_regex('maimai_query_chart_regex',
                  desc='[绿黄红紫白]id<歌曲编号> 查询乐曲信息或谱面信息', developers=['mai-bot', 'OasisAkari'])


@msrgex.handle(r"([绿黄红紫白]?)id([0-9]+)")
async def _(message: MessageSession):
    groups = message.matched_msg.groups()
    level_labels = ['绿', '黄', '红', '紫', '白']
    if groups[0] != "":
        try:
            level_index = level_labels.index(groups[0])
            level_name = ['Basic', 'Advanced', 'Expert', 'Master', 'Re: MASTER']
            name = groups[1]
            music = total_list.by_id(name)
            chart = music['charts'][level_index]
            ds = music['ds'][level_index]
            level = music['level'][level_index]
            file = f"https://www.diving-fish.com/covers/{music['id']}.jpg"
            if len(chart['notes']) == 4:
                msg = f'''{level_name[level_index]} {level}({ds})
TAP: {chart['notes'][0]}
HOLD: {chart['notes'][1]}
SLIDE: {chart['notes'][2]}
BREAK: {chart['notes'][3]}
谱师: {chart['charter']}'''
            else:
                msg = f'''{level_name[level_index]} {level}({ds})
TAP: {chart['notes'][0]}
HOLD: {chart['notes'][1]}
SLIDE: {chart['notes'][2]}
TOUCH: {chart['notes'][3]}
BREAK: {chart['notes'][4]}
谱师: {chart['charter']}'''
            await message.sendMessage([Plain(f"{music['id']}. {music['title']}\n"), BImage(f"{file}"), Plain(msg)])
        except Exception:
            await message.sendMessage("未找到该谱面")
    else:
        name = groups[1]
        music = total_list.by_id(name)
        try:
            file = f"https://www.diving-fish.com/covers/{music['id']}.jpg"
            await message.sendMessage([Plain(f"{music['id']}. {music['title']}\n"),
                                       BImage(f"{file}"),
                                       Plain(f"艺术家: {music['basic_info']['artist']}\n"
                                             f"分类: {music['basic_info']['genre']}\n"
                                             f"BPM: {music['basic_info']['bpm']}\n"
                                             f"版本: {music['basic_info']['from']}\n"
                                             f"难度: {'/'.join(music['level'])}")])
        except Exception:
            await message.sendMessage("未找到该乐曲")


wm_list = ['拼机', '推分', '越级', '下埋', '夜勤', '练底力', '练手法', '打旧框', '干饭', '抓绝赞', '收歌']

today = on_command('maimai_today', alias=['今日舞萌', '今日mai'], desc='查看今天的舞萌运势', developers=['mai-bot', 'OasisAkari'])


@today.handle()
async def _(msg: MessageSession):
    qq = int(msg.session.sender)
    h = hash(qq)
    rp = h % 100
    wm_value = []
    for i in range(11):
        wm_value.append(h & 3)
        h >>= 2
    s = f"今日人品值：{rp}\n"
    for i in range(11):
        if wm_value[i] == 3:
            s += f'宜 {wm_list[i]}\n'
        elif wm_value[i] == 0:
            s += f'忌 {wm_list[i]}\n'
    s += "刘大鸽提醒您：打机时不要大力拍打或滑动哦\n今日推荐歌曲："
    music = total_list[h % len(total_list)]
    await msg.sendMessage([Plain(s)] + song_txt(music))


music_aliases = defaultdict(list)
f = open('assets/maimai/static/aliases.csv', 'r', encoding='utf-8')
tmp = f.readlines()
f.close()
for t in tmp:
    arr = t.strip().split('\t')
    for i in range(len(arr)):
        if arr[i] != "":
            music_aliases[arr[i].lower()].append(arr[0])

mfsrgx = on_regex('maimai_find_song_regex', desc='<歌曲别名>是什么歌 查询乐曲别名对应的乐曲', developers=['mai-bot', 'OasisAkari'])


@mfsrgx.handle(r"(.+)是什么歌")
async def _(msg: MessageSession):
    name = msg.matched_msg.groups()[0].strip().lower()
    if name not in music_aliases:
        await msg.sendMessage("未找到此歌曲\n舞萌 DX 歌曲别名收集计划：https://docs.qq.com/sheet/DQ0pvUHh6b1hjcGpl")
        return
    result_set = music_aliases[name]
    if len(result_set) == 1:
        music = total_list.by_title(result_set[0])
        await msg.sendMessage([Plain('您要找的是不是')] + song_txt(music))
    else:
        s = '\n'.join(result_set)
        await msg.sendMessage(f"您要找的可能是以下歌曲中的其中一首：\n{s}")


sline = on_command('maimai_scoreline', alias='分数线', developers=['mai-bot', 'OasisAkari'])


@sline.handle(['<难度+歌曲id> <分数线>', '帮助'])
async def _(msg: MessageSession):
    r = "([绿黄红紫白])(id)?([0-9]+)"
    arg1 = msg.parsed_msg['<难度+歌曲id>']
    args2 = msg.parsed_msg['<分数线>']
    argh = msg.parsed_msg['帮助']
    if argh:
        s = '''此功能为查找某首歌分数线设计。
命令格式：分数线 <难度+歌曲id> <分数线>
例如：分数线 紫799 100
命令将返回分数线允许的 TAP GREAT 容错以及 BREAK 50落等价的 TAP GREAT 数。
以下为 TAP GREAT 的对应表：
GREAT/GOOD/MISS
TAP\t1/2.5/5
HOLD\t2/5/10
SLIDE\t3/7.5/15
TOUCH\t1/2.5/5
BREAK\t5/12.5/25(外加200落)'''
        await msg.sendMessage([BImage(text_to_image(s))])
    elif args2 is not None:
        try:
            grp = re.match(r, arg1).groups()
            level_labels = ['绿', '黄', '红', '紫', '白']
            level_labels2 = ['Basic', 'Advanced', 'Expert', 'Master', 'Re:MASTER']
            level_index = level_labels.index(grp[0])
            chart_id = grp[2]
            line = float(arg1)
            music = total_list.by_id(chart_id)
            chart: Dict[Any] = music['charts'][level_index]
            tap = int(chart['notes'][0])
            slide = int(chart['notes'][2])
            hold = int(chart['notes'][1])
            touch = int(chart['notes'][3]) if len(chart['notes']) == 5 else 0
            brk = int(chart['notes'][-1])
            total_score = 500 * tap + slide * 1500 + hold * 1000 + touch * 500 + brk * 2500
            break_bonus = 0.01 / brk
            break_50_reduce = total_score * break_bonus / 4
            reduce = 101 - line
            if reduce <= 0 or reduce >= 101:
                raise ValueError
            await msg.sendMessage(f'''{music['title']} {level_labels2[level_index]}
分数线 {line}% 允许的最多 TAP GREAT 数量为 {(total_score * reduce / 10000):.2f}(每个-{10000 / total_score:.4f}%),
BREAK 50落(一共{brk}个)等价于 {(break_50_reduce / 100):.3f} 个 TAP GREAT(-{break_50_reduce / total_score * 100:.4f}%)''')
        except Exception:
            await msg.sendMessage("格式错误，输入“分数线 帮助”以查看帮助信息")


b40 = on_command('maimai_b40', developers=['mai-bot', 'OasisAkari'])


@b40.handle('<username>')
async def _(msg: MessageSession):
    username = msg.parsed_msg['<username>']
    if username == "":
        payload = {'qq': msg.session.sender}
    else:
        payload = {'username': username}
    img, success = await generate(payload)
    if success == 400:
        await msg.sendMessage("未找到此玩家，请确保此玩家的用户名和查分器中的用户名相同。")
    elif success == 403:
        await msg.sendMessage("该用户禁止了其他人获取数据。")
    else:
        await msg.sendMessage([BImage(img)])
