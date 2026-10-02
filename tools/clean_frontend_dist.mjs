import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..','frontend');
const target=path.join(root,'dist');
if(path.dirname(target)!==root)throw new Error(`refusing to clean unexpected path: ${target}`);

function removeTree(entry){
  if(!fs.existsSync(entry))return;
  const stat=fs.lstatSync(entry);
  if(stat.isDirectory()&&!stat.isSymbolicLink()){
    for(const child of fs.readdirSync(entry))removeTree(path.join(entry,child));
    fs.rmdirSync(entry);
  }else fs.unlinkSync(entry);
}

removeTree(target);
