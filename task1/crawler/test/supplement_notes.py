"""通过用户 Chrome CDP 或人工保存 HTML 补齐游客记录，不重新访问官方 URL。"""
import argparse
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.parse import urlsplit
from contextlib import nullcontext

from ..dynamic_crawler import ExistingChrome
from ..document_pipeline import process


def run(base: Path, mode: str, endpoint: str, html_dir: Path | None) -> Path:
    root = base.parent / datetime.now().strftime('supplement_%Y%m%d_%H%M%S_%f')
    (root/'raw').mkdir(parents=True)
    logging.basicConfig(filename=root/'error.log', level=logging.INFO, encoding='utf-8', force=True)
    rows = json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    previous_success = set()
    if (base/'report.json').exists():
        previous_success = {r['url'] for r in json.loads((base/'report.json').read_text(encoding='utf-8')) if r['status']=='success'}
    mapping = []
    for row in rows:
        row.pop('error', None)
        row.pop('failure_stage', None)
        if row['source_type'] == 'official':
            old = Path(row['raw_file'])
            target = root/'raw'/old.name
            shutil.copy2(old, target)
            row['raw_file'] = str(target.resolve())
            continue
        note = urlsplit(row['url']).path.rsplit('/',1)[-1]
        mapping.append(dict(note_id=note, original_url=row['url'], scenic_spot=row['scenic_spot'], filename=note+'.html'))
        # 补采只访问失败项；已验证成功的游客快照也与官方快照一样复用。
        if row['url'] in previous_success:
            target=root/'raw'/(note+'.html')
            shutil.copy2(Path(row['raw_file']), target)
            row.update(raw_file=str(target.resolve()), reused_success=True)
            continue
        # 旧失败页不能当作本轮原件，保留来源路径供追溯。
        row['previous_raw_file'] = row.pop('raw_file', None)
        row['crawler_type'] = 'dynamic'
    (root/'import_map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
    session_info = dict(mode=mode, endpoint=endpoint if mode=='cdp' else None, connected=False,
                        login_state='未读取或导出 cookie；是否登录由用户在连接实例中自行确认')
    try:
        manager = ExistingChrome(endpoint) if mode=='cdp' else nullcontext(None)
        with manager as chrome:
            session_info['connected'] = mode=='cdp'
            for row in rows:
                if row['source_type']=='official' or row.get('reused_success'):
                    continue
                note = urlsplit(row['url']).path.rsplit('/',1)[-1]
                target = root/'raw'/(note+'.html')
                row['crawl_time'] = datetime.now().astimezone().isoformat()
                try:
                    if mode=='cdp':
                        chrome.fetch_html(row['url'],snapshot_path=target)
                        row['notes']='通过用户主动启动的本机 Chrome CDP 会话获取 DOM；未读取或复制 cookie。'
                    else:
                        source = html_dir/(note+'.html')
                        if not source.is_file():
                            raise FileNotFoundError(f'尚未提供人工保存页面：{source}')
                        shutil.copy2(source, target)
                        row['notes']='来自用户正常浏览器会话人工保存的 HTML；dynamic 表示浏览器渲染来源；crawl_time 为本次导入时间。'
                        row['original_url']=row['url']
                    row['raw_file']=str(target.resolve())
                except Exception as exc:
                    row['error']=str(exc)
                    if target.exists():row['raw_file']=str(target.resolve())
                    logging.exception('游客采集/导入失败 %s',note)
                print(note, 'failed' if 'error' in row else 'saved',flush=True)
                if mode=='cdp':sleep(1)
    except Exception as exc:
        session_info['connection_error']=str(exc)
        logging.exception('连接用户 Chrome 失败')
        for row in rows:
            if row['source_type']=='user_generated' and not row.get('reused_success'):
                row.update(error='未能连接用户主动开启的 CDP 会话：'+str(exc),crawl_time=datetime.now().astimezone().isoformat())
    (root/'session.json').write_text(json.dumps(session_info,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    report=process(root.resolve())
    results=[]
    for row,result in zip(rows,report):
        if row['source_type']=='user_generated':
            results.append(dict(note_id=urlsplit(row['url']).path.rsplit('/',1)[-1],**result))
    (root/'notes_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(root.resolve(),flush=True)
    return root


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--base',type=Path,default=Path('task1/crawler/results/formal_20261103_170856'))
    cli.add_argument('--mode',choices=['cdp','local'],default='cdp')
    cli.add_argument('--endpoint',default='http://127.0.0.1:9222')
    cli.add_argument('--html-dir',type=Path)
    args=cli.parse_args()
    if args.mode=='local' and args.html_dir is None:cli.error('local 模式必须指定 --html-dir')
    run(args.base.resolve(),args.mode,args.endpoint,args.html_dir)
