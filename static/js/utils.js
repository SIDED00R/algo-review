const TIER_GROUPS = {
  bronze: [1, 5], silver: [6, 10], gold: [11, 15],
  platinum: [16, 20], diamond: [21, 25], ruby: [26, 30], unrated: [0, 0],
};

function tierClass(tier) {
  if (tier === 0) return '';
  if (tier <= 5) return 'tier-bronze';
  if (tier <= 10) return 'tier-silver';
  if (tier <= 15) return 'tier-gold';
  if (tier <= 20) return 'tier-platinum';
  if (tier <= 25) return 'tier-diamond';
  return 'tier-ruby';
}

// CF 레이팅 → 공식 색상 계열 클래스 (newbie ~ grandmaster)
function cfRatingClass(rating) {
  if (!rating || rating < 1200) return 'cf-newbie';
  if (rating < 1400) return 'cf-pupil';
  if (rating < 1600) return 'cf-specialist';
  if (rating < 1900) return 'cf-expert';
  if (rating < 2100) return 'cf-candidate-master';
  if (rating < 2400) return 'cf-master';
  return 'cf-grandmaster';
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

function cfRefToUrl(ref) {
  const m = String(ref || '').replace(/[^0-9A-Za-z]/g, '').match(/^(\d+)([A-Za-z][A-Za-z0-9]*)$/);
  return m ? `https://codeforces.com/problemset/problem/${m[1]}/${m[2].toUpperCase()}` : '';
}

function problemUrl(problem) {
  if (problem.problem_url) return problem.problem_url;
  if (problem.platform === 'codeforces') {
    const url = cfRefToUrl(problem.problem_ref);
    if (url) return url;
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
