const fs = require('fs');
const glob = require('glob');

const files = glob.sync('src/**/*.{astro,tsx}');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');
  let original = content;

  // Corporate Hub
  content = content.replace(/href="\/"/g, 'href="https://atelierlogicgroup.com/"');
  
  // ReluLayer Product
  content = content.replace(/href="\/relulayer"/g, 'href="https://relulayer.ai/"');
  content = content.replace(/href="\/relulayer\/"/g, 'href="https://relulayer.ai/"');

  // Capability Statement
  content = content.replace(/href="\/capability-statement"/g, 'href="/capability-statement/"');
  // Avoid double slashes if it was already replaced
  content = content.replace(/href="\/capability-statement\/\/"/g, 'href="/capability-statement/"');

  // SBLO Contact Form
  content = content.replace(/href="\/#sblo-form"/g, 'href="https://atelierlogicgroup.com/#sblo-form"');

  // Other trailing slashes for directory format if they are internal pages?
  // Let's also do /compliance, /privacy, /terms
  content = content.replace(/href="\/compliance"/g, 'href="/compliance/"');
  content = content.replace(/href="\/compliance\/\/"/g, 'href="/compliance/"');
  content = content.replace(/href="\/privacy"/g, 'href="/privacy/"');
  content = content.replace(/href="\/privacy\/\/"/g, 'href="/privacy/"');
  content = content.replace(/href="\/terms"/g, 'href="/terms/"');
  content = content.replace(/href="\/terms\/\/"/g, 'href="/terms/"');

  if (content !== original) {
    fs.writeFileSync(file, content, 'utf8');
    console.log('Updated', file);
  }
});
