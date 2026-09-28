// 本程序及代码是在人工智能工具辅助下完成的。工具：OpenAI Codex；模型/版本和版本颁布日期：待赛队按任务记录核实；开发机构：OpenAI。
import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';

const input='2026年中国研究生数学建模竞赛赛题/D题/结果提交模板.xlsx';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const info=await wb.inspect({kind:'workbook,sheet,table',maxChars:5000,tableMaxRows:3,tableMaxCols:11});
console.log(info.ndjson);
const pic=await wb.render({sheetName:'Q1_单点组批',range:'A1:I4',scale:1.5,format:'png'});
await fs.writeFile('D题求解/结果/模板原貌_Q1.png',new Uint8Array(await pic.arrayBuffer()));
