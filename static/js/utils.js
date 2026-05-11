function tierClass(tier) {
  if (tier === 0) return '';
  if (tier <= 5) return 'tier-bronze';
  if (tier <= 10) return 'tier-silver';
  if (tier <= 15) return 'tier-gold';
  if (tier <= 20) return 'tier-platinum';
  if (tier <= 25) return 'tier-diamond';
  return 'tier-ruby';
}

function effClass(e) {
  return { good: 'eff-good', ok: 'eff-ok', poor: 'eff-poor' }[e] || '';
}

function effLabel(e) {
  return { good: '● 효율적', ok: '◐ 보통', poor: '● 비효율적' }[e] || e;
}

function problemLabel(problem) {
  if (problem.platform === 'codeforces') return problem.problem_ref;
  return String(problem.problem_id ?? problem.problem_ref ?? '');
}

function problemUrl(problem) {
  if (problem.problem_url) return problem.problem_url;
  if (problem.platform === 'codeforces') {
    const ref = String(problem.problem_ref || '').replace(/[^0-9A-Za-z]/g, '');
    const match = ref.match(/^(\d+)([A-Za-z][A-Za-z0-9]*)$/);
    if (match) return `https://codeforces.com/problemset/problem/${match[1]}/${match[2].toUpperCase()}`;
  }
  return `https://boj.kr/${problem.problem_id ?? problem.problem_ref}`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setLoading(btn, loading) {
  btn.disabled = loading;
  btn.innerHTML = loading
    ? '<span class="spinner"></span> 분석 중...'
    : btn.dataset.label;
}

function showError(container, msg) {
  container.innerHTML = `<div class="alert alert-error">❌ ${msg}</div>`;
  container.classList.remove('hidden');
}

function detectLanguage(code) {
  if (/#include/.test(code) || /\bstd::/.test(code) || /\bcout\b/.test(code) ||
      /\bcin\b/.test(code) || /\bint\s+main\s*\(/.test(code) || /\bvector\s*</.test(code) ||
      /\busing\s+namespace\s+std/.test(code)) return 'GNU C++17';
  if (/\bdef\s+\w/.test(code) || /\bimport\s+\w/.test(code) ||
      /\bprint\s*\(/.test(code) || /\binput\s*\(/.test(code) ||
      /\brange\s*\(/.test(code)) return 'Python 3';
  if (/\bpublic\s+class\b/.test(code) || /\bSystem\.out\b/.test(code) ||
      /\bScanner\b/.test(code) || /\bBufferedReader\b/.test(code)) return 'Java';
  if (/\bfun\s+main\b/.test(code) || /\bprintln\b/.test(code) ||
      /\breadLine\b/.test(code)) return 'Kotlin';
  if (/\busing\s+System\b/.test(code) || /\bConsole\.\w/.test(code)) return 'C#';
  if (/\bfn\s+main\s*\(/.test(code) || /\buse\s+std::io/.test(code) ||
      /\blet\s+mut\b/.test(code)) return 'Rust';
  if (/\bpackage\s+main\b/.test(code) || /\bfmt\./.test(code)) return 'Go';
  if (/\brequire\s*\(/.test(code) || /\bconsole\.log\b/.test(code)) return 'JavaScript';
  if (/\bprintf\s*\(/.test(code) || /\bscanf\s*\(/.test(code)) return 'C';
  return '';
}
