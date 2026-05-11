/* CodeMirror 에디터 초기화 — 에디터 생성/관리만 담당 */
(function () {
  const LANG_MAP = {
    'GNU C++17': 'text/x-c++src', 'C': 'text/x-csrc', 'C#': 'text/x-csharp',
    'Python 3': 'python', 'PyPy3': 'python',
    'Java': 'text/x-java', 'Kotlin': 'text/x-kotlin',
    'JavaScript': 'javascript', 'TypeScript': 'application/typescript',
    'Rust': 'rust', '': 'python',
  };
  const PM_LANG_MAP = { python3: 'python', cpp: 'text/x-c++src' };

  window.cmEditors = {};

  function isDark() { return !document.body.classList.contains('light'); }

  function createEditor(id, mode) {
    const container = document.getElementById(id);
    if (!container) return;
    const cm = CodeMirror(container, {
      value: '',
      mode: mode || 'python',
      theme: isDark() ? 'dracula' : 'default',
      lineNumbers: true,
      autoCloseBrackets: true,
      matchBrackets: true,
      indentUnit: 4,
      tabSize: 4,
      indentWithTabs: false,
      lineWrapping: false,
      styleActiveLine: true,
      extraKeys: {
        'Ctrl-/': 'toggleComment',
        'Cmd-/': 'toggleComment',
        'Ctrl-Space': cm => CodeMirror.showHint(cm, CodeMirror.hint.anyword, { completeSingle: false }),
      },
    });

    cm.on('inputRead', (editor, change) => {
      if (!editor.state.completionActive && /\w/.test(change.text[0])) {
        CodeMirror.showHint(editor, CodeMirror.hint.anyword, { completeSingle: false });
      }
    });

    window.cmEditors[id] = cm;
    return cm;
  }

  window.getEditorValue = id => window.cmEditors[id]?.getValue() ?? '';
  window.setEditorValue = (id, value) => {
    const cm = window.cmEditors[id];
    if (!cm) return;
    cm.setValue(value ?? '');
    setTimeout(() => cm.refresh(), 0);
  };
  window.switchEditorLang = (id, mode) => window.cmEditors[id]?.setOption('mode', mode);

  createEditor('code-input', 'python');
  createEditor('pm-code', 'python');

  document.getElementById('code-language')?.addEventListener('change', e => {
    window.switchEditorLang('code-input', LANG_MAP[e.target.value] || 'python');
  });
  document.getElementById('pm-language')?.addEventListener('change', e => {
    window.switchEditorLang('pm-code', PM_LANG_MAP[e.target.value] || 'python');
  });

  new MutationObserver(() => {
    const theme = isDark() ? 'dracula' : 'default';
    Object.values(window.cmEditors).forEach(cm => cm.setOption('theme', theme));
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });

  const modal = document.getElementById('problem-modal');
  if (modal) {
    new MutationObserver(() => {
      if (!modal.classList.contains('hidden')) {
        setTimeout(() => window.cmEditors['pm-code']?.refresh(), 50);
      }
    }).observe(modal, { attributes: true, attributeFilter: ['class'] });
  }
})();
