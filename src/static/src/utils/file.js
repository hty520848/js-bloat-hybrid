const fs=require('fs'),path=require('path');
function getAllFiles(dirname,recurse=false,listOfFiles=[]) {
 if(process.env.SQJ_SCOPE_FILES) {
  const spec=JSON.parse(fs.readFileSync(process.env.SQJ_SCOPE_FILES,'utf8'));
  const root=process.env.SQJ_PUBLISHED_ROOT;
  return spec.files.map(rel=>path.join(root,rel)).filter(p=>p===dirname||p.startsWith(dirname+path.sep));
 }
 for(const item of fs.readdirSync(dirname,{withFileTypes:true})) {
  const p=path.join(dirname,item.name);
  if(item.isDirectory()&&recurse&&!['node_modules','.git','coverage','.nyc_output'].includes(item.name)) getAllFiles(p,true,listOfFiles);
  else if(item.isFile()&&item.name.endsWith('.js')) listOfFiles.push(p);
 }
 return [...new Set(listOfFiles)];
}
exports.getDir=p=>path.resolve(process.cwd(),p);
exports.getAllFiles=getAllFiles;
// Raw walker used only by the reviewer-2.2.1 ablation hook. It ignores
// SQJ_SCOPE_FILES on purpose: the ablation needs call sites that live outside
// the production scope to exist in the graph, otherwise the module-scope
// switch has nothing to filter and every arm is identical by construction.
function getAllFilesRaw(dirname,recurse=false,listOfFiles=[]) {
 let entries
 try { entries=fs.readdirSync(dirname,{withFileTypes:true}) } catch { return listOfFiles }
 for(const item of entries) {
  const p=path.join(dirname,item.name)
  // node_modules is skipped while recursing so that a client root contributes
  // its own sources and tests without walking every installed package. Pass a
  // package directory explicitly if it must be parsed.
  if(item.isDirectory()&&recurse&&!['node_modules','.git','coverage','.nyc_output'].includes(item.name)) getAllFilesRaw(p,true,listOfFiles)
  else if(item.isFile()&&item.name.endsWith('.js')) listOfFiles.push(p)
 }
 return [...new Set(listOfFiles)]
}
exports.getAllFilesRaw=getAllFilesRaw;
exports.checkDirectoryValidate=p=>fs.lstatSync(p).isDirectory();
