import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = path.join(root, "node_modules/material-icon-theme/dist/material-icons.json");
const iconsSrc = path.join(root, "node_modules/material-icon-theme/icons");
const iconsDest = path.join(root, "public/material-icons");
const mapDest = path.join(root, "src/assets/material-icon-map.json");

if (!fs.existsSync(src) || !fs.existsSync(iconsSrc)) {
  console.warn("[prepare-material-icons] material-icon-theme not installed, skip");
  process.exit(0);
}

const data = JSON.parse(fs.readFileSync(src, "utf8"));
const light = data.light || {};
const mergeMap = (base = {}, override = {}) => ({ ...base, ...override });
const slim = {
  file: light.file || data.file || "file",
  folder: light.folder || data.folder || "folder",
  folderExpanded: light.folderExpanded || data.folderExpanded || "folder-open",
  fileNames: mergeMap(data.fileNames, light.fileNames),
  fileExtensions: mergeMap(data.fileExtensions, light.fileExtensions),
  folderNames: mergeMap(data.folderNames, light.folderNames),
  folderNamesExpanded: mergeMap(data.folderNamesExpanded, light.folderNamesExpanded),
};

fs.mkdirSync(path.dirname(mapDest), { recursive: true });
fs.writeFileSync(mapDest, JSON.stringify(slim));

fs.rmSync(iconsDest, { recursive: true, force: true });
fs.mkdirSync(iconsDest, { recursive: true });
for (const name of fs.readdirSync(iconsSrc)) {
  if (!name.endsWith(".svg")) continue;
  fs.copyFileSync(path.join(iconsSrc, name), path.join(iconsDest, name));
}

console.log(
  `[prepare-material-icons] map=${fs.statSync(mapDest).size}B icons=${fs.readdirSync(iconsDest).length}`,
);
