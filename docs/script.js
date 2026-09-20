const command = document.querySelector('#install-command');
const copy = document.querySelector('#copy-button');

document.querySelectorAll('.install-tabs button').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelector('.install-tabs .active').classList.remove('active');
    tab.classList.add('active');
    command.textContent = tab.dataset.command;
    copy.textContent = '复制命令';
  });
});

copy.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(command.textContent);
    copy.textContent = '已复制';
  } catch {
    copy.textContent = '请手动复制';
  }
});
