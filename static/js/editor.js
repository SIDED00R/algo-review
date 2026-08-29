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
      // 숫자 리터럴 입력 중에는 자동완성하지 않음 (식별자는 숫자로 시작 불가)
      if (/^\d/.test(prefix)) return;

      const anyResult = CodeMirror.hint.anyword(cm) || { list: [], from: cursor, to: cursor };
      // anyword는 문서 전체 단어를 반환하므로 prefix + 식별자 형태로 필터 (숫자 리터럴 제외)
      const docWords = anyResult.list.filter(w => w.startsWith(prefix) && !/^\d/.test(w));
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
    'Rust': 'rust', 'Go': 'go', 'Swift': 'swift', 'Ruby': 'ruby',
    '': 'python',
  };
  const PM_LANG_MAP = { python3: 'python', cpp: 'text/x-c++src' };

  window.cmEditors = {};

  const INDENT_WIDTH = 4;

  // 들여쓰기 단위는 탭 1칸이다. 선행 공백이 전부 INDENT_WIDTH 의 배수가 아니면 변환하지
  // 않는다 — 어중간한 폭을 탭/스페이스로 섞으면 파이썬이 TabError 로 거부한다.
  function tabifyIndent(code) {
    const indents = code.match(/^[ \t]+/gm) || [];
    const colOf = ws => {
      let col = 0;
      for (const ch of ws) col = ch === '\t' ? col + INDENT_WIDTH - (col % INDENT_WIDTH) : col + 1;
      return col;
    };
    if (!indents.every(ws => colOf(ws) % INDENT_WIDTH === 0)) return code;
    return code.replace(/^[ \t]+/gm, ws => {
      const col = colOf(ws);
      return '\t'.repeat(Math.floor(col / INDENT_WIDTH)) + ' '.repeat(col % INDENT_WIDTH);
    });
  }

  function isDark() { return document.documentElement.getAttribute('data-theme') !== 'light'; }

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
      indentUnit: INDENT_WIDTH,
      tabSize: INDENT_WIDTH,
      indentWithTabs: true,
      lineWrapping: false,
      styleActiveLine: true,
      extraKeys: {
        'Ctrl-/': 'toggleComment',
        'Cmd-/': 'toggleComment',
        // 기본 Shift-Tab 은 indentAuto(줄 재정렬)다 — 내어쓰기로 바꾼다.
        'Shift-Tab': cm => cm.indentSelection('subtract'),
        // Esc 는 에디터에서 포커스를 뺀다 — Tab·Shift-Tab 은 들여쓰기가 소비한다.
        'Esc': cm => cm.getInputField().blur(),
        // cm._hintFn을 참조해 언어 변경 후에도 올바른 목록 사용
        'Ctrl-Space': cm => CodeMirror.showHint(cm, cm._hintFn, { completeSingle: false }),
      },
    });

    // aria-describedby 는 조상에서 상속되지 않는다 — 포커스를 받는 textarea 에 직접 건다.
    cm.getInputField().setAttribute('aria-describedby', `${id}-escape-help`);

    cm._hintFn = makeHintFn(MODE_WORDS[mode || 'python'] || []);

    cm.on('beforeChange', (editor, change) => {
      if (change.origin === 'paste') {
        change.update(change.from, change.to, tabifyIndent(change.text.join('\n')).split('\n'));
      }
    });

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
    cm.setValue(tabifyIndent(value ?? ''));
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
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  const modal = document.getElementById('problem-modal');
  if (modal) {
    new MutationObserver(() => {
      if (!modal.classList.contains('hidden')) {
        setTimeout(() => window.cmEditors['pm-code']?.refresh(), 50);
      }
    }).observe(modal, { attributes: true, attributeFilter: ['class'] });
  }
})();
