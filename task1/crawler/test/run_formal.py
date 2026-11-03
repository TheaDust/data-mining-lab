"""18 个正式样本：采集原件后复用文档流水线，不采集其他链接。"""
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from time import sleep
from ..static_crawler import fetch_html
from ..dynamic_crawler import fetch_html as fetch_dynamic
from ..document_pipeline import process

NOTES = [
('gugong','6a75c572000000002c004029'),
('gugong','6a16b53c0000000008003c9b'),
('gugong','69df5ab90000000021012e2a'),
('gugong','6a7399c6000000000e03c801'),
('gugong','694fc6e8000000001e024b65'),
('xihu','6ab491ba000000001400278d'),
('xihu','6abf66e4000000001a029a51'),
('xihu','6ab11320000000003303aa7c'),
('xihu','6a86f445000000002202ca93'),
('xihu','69ef3f53000000002301fa69'),
('jiuzhaigou','6ae2a985000000002c023fae'),
('jiuzhaigou','6ac66f3a000000001303e8c9'),
('jiuzhaigou','6aba52470000000002012e4a'),
('jiuzhaigou','6ad59171000000002702312a'),
('jiuzhaigou','6a6040e7000000001002af2d'),
]
OFFICIAL = [
('gugong','北京故宫','北京旅游网','https://www.visitbeijing.com.cn/article/47QrSKGCz9N','visitbeijing_article'),
('xihu','杭州西湖','杭州网','https://hznews.hangzhou.com.cn/wghz/content/2021-04/29/content_7956439.htm','hangzhou_article'),
('jiuzhaigou','九寨沟','九寨沟官网','https://www.jiuzhai.com/intelligent-service/way-of-play','jiuzhai_article'),
]


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--inputs',type=Path,help='可选本地 JSON 输入清单；带分享参数的清单应保存在忽略目录或 *.local.json')
    args=cli.parse_args()
    root = Path(__file__).resolve().parents[1]/'results'/datetime.now().strftime('formal_%Y%m%d_%H%M%S')
    (root/'raw').mkdir(parents=True)
    logging.basicConfig(filename=root/'error.log',level=logging.INFO,encoding='utf-8')
    rows=[]
    for slug,spot,source,url,parser in OFFICIAL:
        rows.append(dict(slug=slug,scenic_spot=spot,source_name=source,url=url,parser=parser,source_type='official',text_type='official_route'))
    for slug,note in NOTES:
        spot=next(r[1] for r in OFFICIAL if r[0]==slug)
        url=f'https://www.xiaohongshu.com/explore/{note}'
        rows.append(dict(slug=slug,scenic_spot=spot,source_name='小红书',url=url,parser='xiaohongshu_note',source_type='user_generated',text_type='travel_note'))
    # 分享参数仅由本地清单传入，不把临时参数固化在可提交的代码里。
    if args.inputs:
        rows=json.loads(args.inputs.read_text(encoding='utf-8'))
    (root/'inputs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    for index,row in enumerate(rows):
        row['crawler_type']='static'
        try:
            html=fetch_html(row['url'], timeout=15)
            path=root/'raw'/f'{index+1:02d}_{row["slug"]}.html'
            path.write_text(html,encoding='utf-8')
            row['raw_file']=str(path.resolve())
        except Exception as exc:
            row['error']=str(exc);row['failure_stage']='crawler'
            logging.exception('采集失败 %s',row['url'])
        row['crawl_time']=datetime.now().astimezone().isoformat()
        (root/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print(index+1,row['slug'],'failed' if 'error' in row else 'saved',flush=True)
        sleep(1)
    process(root.resolve())
    retry_dynamic(root.resolve())
    print(root.resolve(),flush=True)
    return int(any(r['status']=='failed' for r in json.loads((root/'report.json').read_text(encoding='utf-8'))))


def retry_dynamic(root):
    """静态空壳仅用普通 Chrome 再访问一次，不处理登录或验证码。"""
    from ..parsers.formal_parser import FormalParser
    rows=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    for index,row in enumerate(rows):
        if 'error' not in row:
            try:
                FormalParser(row['parser']).parse(Path(row['raw_file']).read_text(encoding='utf-8'))
                continue
            except ValueError:
                pass
        path=root/'raw'/f'{index+1:02d}_{row["slug"]}_dynamic.html'
        row['crawler_type']='dynamic'
        row['static_raw_file']=row.get('raw_file')
        try:
            fetch_dynamic(row['url'],timeout=15000,snapshot_path=path)
            row.pop('error',None)
        except Exception as exc:
            row['error']=str(exc)
            logging.exception('动态访问失败 %s',row['url'])
        if path.exists():row['raw_file']=str(path)
        row['crawl_time']=datetime.now().astimezone().isoformat()
        (root/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print('dynamic',index+1,flush=True)
        sleep(1)
    process(root)


if __name__=='__main__':
    raise SystemExit(main())
