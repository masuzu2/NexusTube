/**
 * Packs dist_electron/win-unpacked into NexusTube_Setup_v3.4.0.msi.
 * node.exe in that folder is a hardlink of NexusTube.exe, so it is left out.
 * The app creates that link itself on first launch.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const root = path.resolve(__dirname);
const sourceDir = path.join(root, 'dist_electron', 'win-unpacked');
const installerDir = path.join(root, 'installer');
const wixDir = path.join(installerDir, '.wix_tools');
const version = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version;
const msiName = `NexusTube_Setup_v${version}.msi`;
const skipNames = new Set(['node.exe', 'debug.log']);

function xml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function wid(prefix, rel) {
  const hash = crypto.createHash('sha1').update(rel.replace(/\\/g, '/')).digest('hex').slice(0, 12);
  return prefix + hash;
}

function walk(dir) {
  const files = [];
  const dirs = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      dirs.push(full);
      const nested = walk(full);
      files.push(...nested.files);
      dirs.push(...nested.dirs);
    } else if (!skipNames.has(entry.name)) {
      files.push(full);
    }
  }
  return { files, dirs };
}

function writeBmp(file, width, height, paint) {
  const stride = Math.ceil((width * 3) / 4) * 4;
  const pixels = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const [r, g, b] = paint(x, y, width, height);
      const offset = (height - 1 - y) * stride + x * 3;
      pixels[offset] = b;
      pixels[offset + 1] = g;
      pixels[offset + 2] = r;
    }
  }
  const header = Buffer.alloc(54);
  header.write('BM', 0);
  header.writeUInt32LE(54 + pixels.length, 2);
  header.writeUInt32LE(54, 10);
  header.writeUInt32LE(40, 14);
  header.writeInt32LE(width, 18);
  header.writeInt32LE(height, 22);
  header.writeUInt16LE(1, 26);
  header.writeUInt16LE(24, 28);
  header.writeUInt32LE(pixels.length, 34);
  header.writeUInt32LE(2835, 38);
  header.writeUInt32LE(2835, 42);
  fs.writeFileSync(file, Buffer.concat([header, pixels]));
}

function paintDesk(x, y, width, height) {
  const ground = [26, 22, 19];
  const copper = [224, 122, 61];
  if (x < 8 || y > height - 6) return copper;
  if (y < 2) return copper;
  return ground;
}

function harvest() {
  if (!fs.existsSync(path.join(sourceDir, 'NexusTube.exe'))) {
    throw new Error('dist_electron\\win-unpacked\\NexusTube.exe is missing');
  }
  const packed = walk(sourceDir);
  const files = packed.files.map((full) => ({ full, rel: path.relative(sourceDir, full) }));
  const engineDir = path.join(process.env.APPDATA || '', 'NexusTube', 'bin');
  for (const name of ['yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe']) {
    const full = path.join(engineDir, name);
    if (!fs.existsSync(full)) throw new Error(`missing engine ${full}`);
    files.push({ full, rel: path.join('bin', name) });
  }
  const componentIds = [];
  const chunks = [];
  chunks.push('<?xml version="1.0" encoding="utf-8"?>');
  chunks.push('<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">');
  chunks.push('  <Fragment>');
  chunks.push('    <DirectoryRef Id="INSTALLDIR">');

  const byDir = new Map();
  const dirSet = new Set();
  for (const file of files) {
    const relDir = path.dirname(file.rel);
    const key = relDir === '.' ? '' : relDir;
    if (!byDir.has(key)) byDir.set(key, []);
    byDir.get(key).push(file);
    if (key) dirSet.add(key);
  }

  function fileXml(file, indent) {
    const rel = file.rel;
    const base = path.basename(file.full);
    const isExe = rel === 'NexusTube.exe';
    const componentId = isExe ? 'NexusTubeExeComp' : wid('cmp', rel);
    const fileId = isExe ? 'NexusTubeExeFile' : wid('fil', rel);
    const guid = isExe ? 'Guid="{B2C3D4E5-F6A7-8901-BCDE-F12345678901}"' : 'Guid="*"';
    componentIds.push(componentId);
    const lines = [
      `${indent}<Component Id="${componentId}" ${guid} Win64="yes">`,
      `${indent}  <File Id="${fileId}" Name="${xml(base)}" Source="${xml(file.full)}" KeyPath="yes" />`
    ];
    if (isExe) {
      lines.push(`${indent}  <RegistryValue Root="HKLM" Key="Software\\by herlove\\NexusTube" Name="InstallDir" Type="string" Value="[INSTALLDIR]" />`);
      lines.push(`${indent}  <RegistryValue Root="HKLM" Key="Software\\by herlove\\NexusTube" Name="Version" Type="string" Value="${xml(version)}" />`);
    }
    lines.push(`${indent}</Component>`);
    return lines.join('\n');
  }

  function dirXml(relDir, indent) {
    const lines = [];
    if (relDir) {
      const name = path.basename(relDir);
      const id = wid('dir', relDir);
      const cleanId = wid('cld', relDir);
      componentIds.push(cleanId);
      lines.push(`${indent}<Directory Id="${id}" Name="${xml(name)}">`);
      lines.push(`${indent}  <Component Id="${cleanId}" Guid="*" Win64="yes">`);
      lines.push(`${indent}    <RemoveFolder Id="${wid('rmd', relDir)}" On="uninstall" />`);
      lines.push(`${indent}    <RegistryValue Root="HKLM" Key="Software\\by herlove\\NexusTube\\dirs" Name="${xml(relDir.replace(/\\/g, '/'))}" Type="integer" Value="1" KeyPath="yes" />`);
      lines.push(`${indent}  </Component>`);
      indent += '  ';
    }
    for (const file of byDir.get(relDir) || []) lines.push(fileXml(file, indent));
    const childDirs = [...dirSet]
      .filter((rel) => path.dirname(rel) === (relDir || '.'))
      .sort();
    for (const child of childDirs) lines.push(dirXml(child, indent));
    if (relDir) lines.push(`${indent.slice(2)}</Directory>`);
    return lines.join('\n');
  }

  chunks.push(dirXml('', '      '));
  chunks.push('    </DirectoryRef>');
  chunks.push('    <ComponentGroup Id="ElectronApp">');
  for (const id of componentIds) chunks.push(`      <ComponentRef Id="${id}" />`);
  chunks.push('    </ComponentGroup>');
  chunks.push('  </Fragment>');
  chunks.push('</Wix>');
  const out = path.join(installerDir, 'ElectronFiles.wxs');
  fs.writeFileSync(out, chunks.join('\n'), 'utf8');
  return { out, count: files.length };
}

function ensureArt() {
  const iconSrc = fs.existsSync(path.join(root, 'icon.ico'))
    ? path.join(root, 'icon.ico')
    : path.join(root, 'NexusTube by herlove.ico');
  fs.copyFileSync(iconSrc, path.join(installerDir, 'NexusTube.ico'));
  writeBmp(path.join(installerDir, 'WixUIDialog.bmp'), 493, 312, paintDesk);
  writeBmp(path.join(installerDir, 'WixUIBanner.bmp'), 493, 58, paintDesk);
}

function run(bin, args) {
  const result = spawnSync(bin, args, {
    cwd: installerDir,
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
    windowsHide: true
  });
  const text = `${result.stdout || ''}\n${result.stderr || ''}`.trim();
  if (result.status !== 0) {
    throw new Error(`${path.basename(bin)} failed\n${text}`);
  }
  if (text) console.log(text);
}

function main() {
  const candle = path.join(wixDir, 'candle.exe');
  const light = path.join(wixDir, 'light.exe');
  if (!fs.existsSync(candle) || !fs.existsSync(light)) {
    throw new Error('WiX tools are missing from installer\\.wix_tools');
  }
  ensureArt();
  const harvested = harvest();
  console.log(`harvested ${harvested.count} files`);
  const objDir = path.join(installerDir, 'obj');
  fs.mkdirSync(objDir, { recursive: true });
  run(candle, [
    '-nologo', '-arch', 'x64',
    '-ext', 'WixUIExtension',
    '-ext', 'WixUtilExtension',
    `-dProductVersion=${version}`,
    '-out', `${objDir}\\`,
    path.join(installerDir, 'NexusTube.wxs'),
    harvested.out
  ]);
  const msiPath = path.join(root, msiName);
  run(light, [
    '-nologo', '-spdb', '-cultures:en-us',
    '-ext', 'WixUIExtension',
    '-ext', 'WixUtilExtension',
    '-sice:ICE03', '-sice:ICE57', '-sice:ICE61', '-sice:ICE91',
    '-sw1076', '-sw1079',
    '-out', msiPath,
    path.join(objDir, 'NexusTube.wixobj'),
    path.join(objDir, 'ElectronFiles.wixobj')
  ]);
  fs.mkdirSync(path.join(root, 'dist'), { recursive: true });
  fs.copyFileSync(msiPath, path.join(root, 'dist', msiName));
  const size = fs.statSync(msiPath).size;
  console.log(`msi ${msiPath}`);
  console.log(`size ${(size / 1024 / 1024).toFixed(1)} MB`);
}

main();
