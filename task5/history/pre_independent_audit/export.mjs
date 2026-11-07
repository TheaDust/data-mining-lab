import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
// Windows 禁止创建 junction 时，使用公开 exports 入口，避免修改全局依赖目录。
const lib = process.env.ARTIFACT_TOOL_ENTRY || 'C:/Users/Jack1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const {Workbook, SpreadsheetFile} = await import(pathToFileURL(lib));
const root=path.dirname(fileURLToPath(import.meta.url));
const out=path.join(root,'results');
const read=async n=>JSON.parse(await fs.readFile(path.join(out,n),'utf8'));
const wb=Workbook.create();
const mapping=await read('final_mapping.json');
const review=await read('human_review.json');
for(const [name,rows,cols] of [
 ['条件建议映射',mapping,['pair_id','condition_type','condition','recommendation','scenic_area','source_type','doc_id','review_status','source_text','sources']],
 ['人工审核',review,['sample_type','pair_id','doc_id','source_text','condition','recommendation','condition_type','human_condition','human_recommendation','error_type','human_label','reviewer','review_status']]
]) {
 const s=wb.worksheets.add(name);
 const values=[cols,...rows.map(r=>cols.map(c=>typeof r[c]==='object'?JSON.stringify(r[c]):r[c]??''))];
 s.getRange('A1').write(values);
 s.getRange(`A1:${String.fromCharCode(64+cols.length)}${values.length}`).format.columnWidth=25;
 s.getRange(`A1:${String.fromCharCode(64+cols.length)}${values.length}`).format.rowHeight=48;
 s.getRange(`A1:${String.fromCharCode(64+cols.length)}${values.length}`).format.wrapText=true;
 s.getRange(`A2:${String.fromCharCode(64+cols.length)}${values.length}`).format.rowHeight=150;
 for (const col of (name==='条件建议映射'?['C','D','I','J']:['D','E','F','H','I'])) s.getRange(`${col}1:${col}${values.length}`).format.columnWidth=50;
 s.getRange(`A1:${String.fromCharCode(64+cols.length)}1`).format.fill='#D9E8F5';
 s.freezePanes.freezeRows(1);
}
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'条件建议映射!A1:F4',tableMaxRows:4,tableMaxCols:6})).ndjson);
const file=await SpreadsheetFile.exportXlsx(wb); await file.save(path.join(out,'final_mapping.xlsx'));
for (const [sheetName,name,range] of [['条件建议映射','excel_preview.png','A1:F4'],['人工审核','review_preview.png','A1:F3']]) {
 try { const preview=await wb.render({sheetName,range,scale:1}); await fs.writeFile(path.join(out,name),new Uint8Array(await preview.arrayBuffer())); } catch(e) { await fs.writeFile(path.join(out,'excel_render_limitation.txt'),String(e)); }
}
