import fs from 'node:fs';
const out = 'www';
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
for (const f of ['index.html', 'almanac.config.js']) fs.copyFileSync(f, `${out}/${f}`);
for (const d of ['js', 'css']) fs.cpSync(d, `${out}/${d}`, { recursive: true });
console.log('www ready:', fs.readdirSync(out).join(', '));
