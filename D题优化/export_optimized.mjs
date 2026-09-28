// AI-assisted code: OpenAI Codex; metadata to be verified by team.
import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const before=process.argv.includes('--before');
const input='原始备份/结果提交模板_已填.xlsx';
const dir='outputs/optimization-20260928';
await fs.mkdir(dir,{recursive:true});
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const columns={Q1_单点组批:'I',Q2_运输架次:'H',Q2_逐箱交付:'D',Q3_中继架次:'K',Q3_通信保障:'F',Q4_分区配置:'K'};
if (before) {
  console.log((await wb.inspect({kind:'workbook,sheet',maxChars:2200,tableMaxRows:2,tableMaxCols:3})).ndjson);
  for(const [name,col] of Object.entries(columns)) {
    const p=await wb.render({sheetName:name,range:`A1:${col}${name.startsWith('Q4')?6:4}`,scale:1.3,format:'png'});
    await fs.writeFile(`${dir}/before_${name}.png`,new Uint8Array(await p.arrayBuffer()));
  }
} else {
  const rows=JSON.parse(await fs.readFile('结果/template_data.json','utf8'));
  for(const [name,data] of Object.entries(rows)) {
    if(name.startsWith('Q1')) continue;
    const sheet=wb.worksheets.getItem(name);
    sheet.getRange(`A2:${columns[name]}1000`).clear({applyTo:'contents'});
    sheet.getRangeByIndexes(1,0,data.length,data[0].length).values=data.map(row=>row.map(v=>v===''?null:v));
    // Repair the inherited 409.5 pt headers only in the changed views.
    if(['Q2_运输架次','Q2_逐箱交付','Q4_分区配置'].includes(name)) sheet.getRange(`A1:${columns[name]}1`).format.rowHeight=30;
    if(name==='Q4_分区配置') {
      sheet.getRange('A2:K6').format.rowHeight=32;
      sheet.getRange('C2:C6').format.wrapText=true;
      sheet.getRange('A2:K6').format.verticalAlignment='center';
    }
  }
  wb.recalculate();
  const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},maxChars:1500});
  console.log(errors.ndjson);
  for(const [name,col] of Object.entries(columns)) {
    console.log((await wb.inspect({kind:'table',sheetId:name,range:`A1:${col}3`,maxChars:1800,tableMaxRows:3,tableMaxCols:11})).ndjson);
    if(name.startsWith('Q1'))continue;
    const p=await wb.render({sheetName:name,range:`A1:${col}${name.startsWith('Q4')?6:5}`,scale:1.3,format:'png'});
    await fs.writeFile(`${dir}/after_${name}.png`,new Uint8Array(await p.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(`${dir}/结果提交模板_优化版.xlsx`);
}
