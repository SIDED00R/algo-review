(function () {
  const PYTHON_WORDS = [
    'False','None','True','and','as','assert','async','await','break','class',
    'continue','def','del','elif','else','except','finally','for','from',
    'global','if','import','in','is','lambda','nonlocal','not','or','pass',
    'raise','return','try','while','with','yield',
    'print','input','len','range','int','str','float','list','dict','set',
    'tuple','bool','type','isinstance','enumerate','zip','map','filter',
    'sorted','reversed','sum','min','max','abs','round','open','append',
    'extend','insert','remove','pop','index','count','sort','upper','lower',
    'strip','split','join','format','replace','startswith','endswith','find',
    'sys','math','collections','defaultdict','Counter','deque','heapq','bisect',
  ];
  const CPP_WORDS = [
    'int','long','double','float','char','bool','void','string','vector','map',
    'set','pair','queue','stack','deque','unordered_map','unordered_set',
    'priority_queue','if','else','for','while','do','return','break','continue',
    'class','struct','namespace','using','include','define','cout','cin','endl',
    'printf','scanf','auto','const','static','typedef','typename','sort',
    'reverse','find','lower_bound','upper_bound','push_back','pop_back',
    'begin','end','size','empty','first','second','make_pair','min','max',
    'abs','swap','ios_base','sync_with_stdio','tie','NULL','nullptr',
  ];

  // mode 문자열 → 키워드 목록 (매핑 없는 언어는 anyword만 사용)
  const MODE_WORDS = {
    'python': PYTHON_WORDS,
    'text/x-c++src': CPP_WORDS,
    'text/x-csrc': CPP_WORDS,
  };

  function makeHintFn(keywords) {
    return function(cm) {
      const cursor = cm.getCursor();
      const token = cm.getTokenAt(cursor);
      if (token.type === 'string' || token.type === 'comment') return;
      const prefix = token.string;
      if (!prefix || prefix.length < 1) return;

      const anyResult = CodeMirror.hint.anyword(cm) || { list: [], from: cursor, to: cursor };
      // anyword는 문서 전체 단어를 반환하므로 prefix로 필터
      const docWords = anyResult.list.filter(w => w.startsWith(prefix));
      const docSet = new Set(docWords);
      const kwMatches = keywords.filter(k => k.startsWith(prefix) && !docSet.has(k));
      const list = [...kwMatches, ...docWords];
      return list.length ? { list, from: anyResult.from, to: anyResult.to } : undefined;
    };
  }

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
        // cm._hintFn을 참조해 언어 변경 후에도 올바른 목록 사용
        'Ctrl-Space': cm => CodeMirror.showHint(cm, cm._hintFn, { completeSingle: false }),
      },
    });

    cm._hintFn = makeHintFn(MODE_WORDS[mode || 'python'] || []);

    cm.on('inputRead', (editor, change) => {
      if (!editor.state.completionActive && /\w/.test(change.text[0])) {
        CodeMirror.showHint(editor, editor._hintFn, { completeSingle: false });
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
  window.switchEditorLang = (id, mode) => {
    const cm = window.cmEditors[id];
    if (!cm) return;
    cm.setOption('mode', mode);
    cm._hintFn = makeHintFn(MODE_WORDS[mode] || []);
  };

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
