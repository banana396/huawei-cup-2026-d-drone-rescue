// 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';

const saved='D题求解/outputs/d-question-20260924/结果提交模板_已填.xlsx';
const input=process.argv.includes('--update-existing')?saved:'2026年中国研究生数学建模竞赛赛题/D题/结果提交模板.xlsx';
const rows=JSON.parse(await fs.readFile('D题求解/结果/template_data.json','utf8'));
const outputDir='D题求解/outputs/d-question-20260924';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const updating=process.argv.includes('--update-existing');
const changed=updating?['Q2_运输架次','Q2_逐箱交付']:Object.keys(rows);
for (const [name,data] of Object.entries(rows)) {
  if (!changed.includes(name)) continue;
  const sheet=wb.worksheets.getItem(name);
  sheet.getRangeByIndexes(1,0,data.length,data[0].length).values=data;
  if (name==='Q3_通信保障') {
    sheet.getRange(`C2:D${data.length+1}`).setNumberFormat('0.000000000');
    sheet.getRange('C:D').format.columnWidth=23;
  }
  console.log(name,data.length);
}
wb.recalculate();
const inspected=await wb.inspect({kind:'table',sheetId:'Q2_运输架次',range:'A1:H5',maxChars:2300,tableMaxRows:5,tableMaxCols:8});
console.log(inspected.ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'formula error scan',maxChars:1000});
console.log(errors.ndjson);
await fs.mkdir(outputDir,{recursive:true});
for (const [name,data] of Object.entries(rows)) {
  if (!changed.includes(name)) continue;
  const last=Math.min(data.length+1,name==='Q4_分区配置'?6:4);
  const col={Q1_单点组批:'I',Q2_运输架次:'H',Q2_逐箱交付:'D',Q3_中继架次:'K',Q3_通信保障:'F',Q4_分区配置:'K'}[name];
  const pic=await wb.render({sheetName:name,range:`A1:${col}${last}`,scale:1.2,format:'png'});
  await fs.writeFile(`${outputDir}/${name}.png`,new Uint8Array(await pic.arrayBuffer()));
}
const result=await SpreadsheetFile.exportXlsx(wb);
await result.save(`${outputDir}/结果提交模板_已填.xlsx`);
