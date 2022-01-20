import os

from config import Config

if not Config('db_path'):
    raise AttributeError('Wait! You need to fill a valid database address into the config.cfg "db_path"\n'
                         'Example: \ndb_path = sqlite:///database/save.db\n'
                         '(Also you can fill in the above example directly,'
                         ' bot will automatically create a SQLite database in the "./database/save.db")')

import asyncio
import traceback
import aioconsole

from datetime import datetime

from init import init_bot
from core.elements import Schedule, StartUp, MsgInfo, Session, PrivateAssets, EnableDirtyWordCheck, Url
from core.console.template import Template as MessageSession, FetchTarget
from core.parser.message import parser
from core.scheduler import Scheduler
from core.loader import ModulesManager
from core.utils import init

EnableDirtyWordCheck.status = True
PrivateAssets.set(os.path.abspath(os.path.dirname(__file__) + '/assets'))
Url.mm = True
init()


async def console_scheduler():
    gather_list = []
    Modules = ModulesManager.return_modules_list_as_dict()
    for x in Modules:
        if isinstance(Modules[x], StartUp):
            gather_list.append(asyncio.ensure_future(
                Modules[x].function(FetchTarget)))
        if isinstance(Modules[x], Schedule):
            Scheduler.add_job(
                func=Modules[x].function, trigger=Modules[x].trigger, args=[FetchTarget])
    await asyncio.gather(*gather_list)
    Scheduler.start()


async def console_command():
    try:
        m = await aioconsole.ainput('> ')
        time = datetime.now()
        await parser(MessageSession(target=MsgInfo(targetId='TEST|0',
                                                   senderId='TEST|0',
                                                   senderName='',
                                                   targetFrom='TEST|Console',
                                                   senderFrom='TEST|Console'),
                                    session=Session(message=m, target='TEST|0', sender='TEST|0')))
        print('----Process end----')
        usage_time = datetime.now() - time
        print('Usage time:', usage_time)
        await console_command()
    except KeyboardInterrupt:
        print('Exited.')
        exit()
    except Exception:
        traceback.print_exc()


init_bot()
loop = asyncio.get_event_loop()
loop.create_task(console_scheduler())
loop.create_task(console_command())
loop.run_forever()
