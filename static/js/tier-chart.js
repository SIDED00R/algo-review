// 커스텀 레이팅 공식:
//   base   = avg(top 20% tiers) × 60           (티어 상한 30 → 사실상 최대 1800, 별도 캡 없음)
//   volume = round(400 × (1 − 0.99^N))         max  400  (N≈460 수렴)
//   trend  = (avg of last 10 tiers − avg_top20) × 8  ±200
//   rating = base + volume + trend

const RATING_TIERS = [
  { min: 2200, label: 'Master' },
  { min: 1700, label: 'Ruby' },
  { min: 1200, label: 'Diamond' },
  { min: 750,  label: 'Platinum' },
  { min: 380,  label: 'Gold' },
  { min: 120,  label: 'Silver' },
  { min: 30,   label: 'Bronze' },
  { min: 0,    label: 'Unrated' },
];

function getTierLabel(score) {
  for (const { min, label } of RATING_TIERS) {
    if (score >= min) return label;
  }
  return 'Unrated';
}

// CSS 변수는 hex 로 오므로 면적 채우기용 알파를 붙이려면 변환이 필요하다
function hexToRgba(hex, alpha) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

let tierChartInstance = null;

// 기본 안내 문구는 index.html 이 정본이다 — 여기에 복제하면 둘이 갈린다. 처음 덮어쓰기
// 전에 한 번 붙잡아 두고, 인자 없이 부르면 그것으로 되돌린다(예전에는 라이브러리 안내문으로
// 덮은 뒤 되돌리지 않아 "기록 없음" 자리에 그 문구가 남았다).
let _defaultEmptyText = null;

/** 차트를 숨기고 안내 문구를 띄운다. text 를 생략하면 기본 문구로 되돌린다. */
function showChartMessage(text) {
  const emptyEl = document.getElementById('tier-chart-empty');
  if (_defaultEmptyText === null) _defaultEmptyText = emptyEl.textContent.trim();
  document.getElementById('tier-chart').classList.add('hidden');
  emptyEl.textContent = text || _defaultEmptyText;
  emptyEl.classList.remove('hidden');
}

async function loadTierChart() {
  if (tierChartInstance) {
    tierChartInstance.destroy();
    tierChartInstance = null;
  }
  try {
    // fetchJsonOk 를 쓴다 — res.ok 를 안 보면 503(온디맨드 DB 정지)이 빈 배열로 흘러
    // "기록이 없습니다"로 표시되고 사용자가 장애를 알 수 없다.
    const data = await fetchJsonOk('/api/tier-history', undefined, '성장 곡선 로딩 실패');
    const history = data.history || [];

    if (!history.length) {
      showChartMessage();
      return;
    }

    document.getElementById('tier-chart').classList.remove('hidden');
    document.getElementById('tier-chart-empty').classList.add('hidden');

    // 문제당 한 점만 쓴다. **첫 등장**을 남긴다 — tier 는 회차가 아니라 문제의 속성이라
    // 값은 어느 회차를 골라도 같고, 바뀌는 건 그 문제가 시계열에 놓이는 날짜뿐이다.
    // 마지막 회차를 남기면 예전 문제를 재제출할 때 그 점이 과거에서 사라져 오늘로 옮겨가고,
    // 이미 지나간 구간의 레이팅이 소급 변한다.
    // 서버가 created_at 오름차순으로 주므로 정순 1패스면 dedupe 와 정렬이 함께 끝난다.
    const seenPids = new Set();
    const deduped = [];
    history.forEach(r => {
      if (!seenPids.has(r.problem_id)) {
        seenPids.add(r.problem_id);
        deduped.push(r);
      }
    });

    const byDate = {};
    deduped.forEach(r => {
      const d = r.created_at.slice(0, 10);
      if (!byDate[d]) byDate[d] = [];
      byDate[d].push(r);
    });

    const uniqueDates = Object.keys(byDate).sort();

    const TREND_WINDOW = 10;
    const tiersSorted = []; // 내림차순 정렬, 상위 20% 계산용
    const lastTiers = [];   // 최근 10문제 큐
    const myTierLine = [];

    for (const d of uniqueDates) {
      for (const r of byDate[d]) {
        // 내림차순 삽입
        let lo = 0, hi = tiersSorted.length;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (tiersSorted[mid] >= r.tier) lo = mid + 1;
          else hi = mid;
        }
        tiersSorted.splice(lo, 0, r.tier);

        // 트렌드 윈도우
        lastTiers.push(r.tier);
        if (lastTiers.length > TREND_WINDOW) lastTiers.shift();
      }

      const N = tiersSorted.length;
      const topN = Math.max(1, Math.floor(N * 0.2));
      const topSlice = tiersSorted.slice(0, topN);
      const avgTop20 = topSlice.reduce((s, v) => s + v, 0) / topN;

      const base = avgTop20 * 60;
      const volume = Math.round(400 * (1 - Math.pow(0.99, N)));

      const avgLast = lastTiers.reduce((s, v) => s + v, 0) / lastTiers.length;
      const trend = Math.max(-200, Math.min(200, Math.round((avgLast - avgTop20) * 8)));

      myTierLine.push({ x: d, y: Math.round(base + volume + trend) });
    }

    const maxScore = myTierLine.length ? Math.max(...myTierLine.map(p => p.y)) : 50;
    const yMax = Math.max(maxScore * 1.2, 50);

    const cssVar = name => getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
    const gridColor = cssVar('--line');
    const textColor = cssVar('--fg-dim');
    const lineColor = cssVar('--eff-good-fg');
    // 면적도 데이터다 — 토큰 색에서 투명도만 낮춰 쓴다
    const fillColor = hexToRgba(lineColor, 0.1);

    const tickValues = RATING_TIERS.map(t => t.min);
    const tickLabels = Object.fromEntries(RATING_TIERS.map(t => [t.min, t.label]));

    if (typeof Chart === 'undefined') {
      showChartMessage('차트 라이브러리를 불러오지 못했습니다. 새로고침해 주세요.');
      return;
    }

    const ctx = document.getElementById('tier-chart').getContext('2d');
    tierChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: '내 레이팅',
          data: myTierLine,
          borderColor: lineColor,
          backgroundColor: fillColor,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          fill: true,
          stepped: 'after',
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: textColor, font: { size: 12 } } },
          tooltip: {
            callbacks: {
              label: ctx => {
                const score = Math.round(ctx.parsed.y);
                return `레이팅: ${score} (${getTierLabel(score)})`;
              },
            },
          },
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'day', displayFormats: { day: 'MM/dd' } },
            ticks: { color: textColor, maxTicksLimit: 10, maxRotation: 0 },
            grid: { color: gridColor },
          },
          y: {
            min: 0,
            suggestedMax: yMax,
            afterBuildTicks(scale) {
              // 티어 경계를 눈금으로 쓰되 너무 붙은 것은 버린다 —
              // 그러지 않으면 축 하단에서 Bronze/Unrated 라벨이 겹쳐 읽을 수 없다.
              const minGap = scale.max * 0.07;
              const kept = [];
              for (const v of [...tickValues].sort((a, b) => a - b)) {
                if (v > scale.max + 20) continue;
                if (kept.length && v - kept[kept.length - 1] < minGap) continue;
                kept.push(v);
              }
              scale.ticks = kept.map(v => ({ value: v }));
            },
            ticks: {
              color: textColor,
              callback: v => tickLabels[v] ?? '',
            },
            grid: { color: gridColor },
          },
        },
      },
    });
  } catch (e) {
    // 예전에는 console.error 만 남겨 사용자에게 아무 반응이 없었다.
    showChartMessage(e.message || '성장 곡선을 불러오지 못했습니다.');
  }
}

// editor.js 와 같은 방식으로 테마 변경을 감시한다. 예전에는 감시자가 없어
// 테마를 토글해도 축·그리드·범례 색이 그대로 남았다(통계 탭을 다시 눌러야 갱신).
new MutationObserver(() => {
  if (tierChartInstance) loadTierChart();
}).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
