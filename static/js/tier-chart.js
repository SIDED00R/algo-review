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
// 전에 한 번 붙잡아 두고, 인자 없이 부르면 그것으로 되돌린다 — 되돌리지 않으면
// 라이브러리 안내문이 "기록 없음" 자리에 그대로 남는다.
let _defaultEmptyText = null;

/** 차트를 숨기고 안내 문구를 띄운다. text 를 생략하면 기본 문구로 되돌린다. */
function showChartMessage(text) {
  const emptyEl = document.getElementById('tier-chart-empty');
  if (_defaultEmptyText === null) _defaultEmptyText = emptyEl.textContent.trim();
  document.getElementById('tier-chart').classList.add('hidden');
  emptyEl.textContent = text || _defaultEmptyText;
  emptyEl.classList.remove('hidden');
}

// 세대 토큰 — problem-modal.js 와 같은 규약. 없으면 탭을 연속으로 열 때 호출 A·B 가
// 둘 다 진입 시점에 tierChartInstance === null 을 보고 destroy 를 건너뛴 뒤, 뒤늦은
// new Chart 가 같은 canvas 에서 "Canvas is already in use" 를 던진다. 그 예외는
// 아래 catch 가 showChartMessage 로 넘겨 **Chart.js 영문 메시지가 안내문 자리에** 뜬다.
let _chartToken = 0;

async function loadTierChart() {
  const token = ++_chartToken;
  if (tierChartInstance) {
    tierChartInstance.destroy();
    tierChartInstance = null;
  }
  try {
    // fetchJsonOk 를 쓴다 — res.ok 를 안 보면 503(온디맨드 DB 정지)이 빈 배열로 흘러
    // "기록이 없습니다"로 표시되고 사용자가 장애를 알 수 없다.
    const data = await fetchJsonOk('/api/tier-history', undefined, '성장 곡선 로딩 실패');
    if (token !== _chartToken) return;
    const history = data.history || [];

    if (!history.length) {
      showChartMessage();
      return;
    }

    document.getElementById('tier-chart').classList.remove('hidden');
    document.getElementById('tier-chart-empty').classList.add('hidden');

    // 서버가 문제당 첫 등장 한 점씩, created_at 오름차순으로 준다(db.get_tier_history).
    // 여기서 다시 거르지 않는다 — 같은 규칙을 두 곳에 두면 한쪽만 바뀌어 갈린다.
    const byDate = {};
    history.forEach(r => {
      const d = localDate(r.created_at);
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
    const lineColor = cssVar('--chart-line');
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
    if (token !== _chartToken) return;
    showChartMessage(e.message || '성장 곡선을 불러오지 못했습니다.');
  }
}

/** 테마 색만 새 토큰 값으로 바꾼다. 데이터는 그대로다. */
function recolorTierChart() {
  const chart = tierChartInstance;
  if (!chart) return;
  const cssVar = name => getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim();
  const gridColor = cssVar('--line');
  const textColor = cssVar('--fg-dim');
  const lineColor = cssVar('--chart-line');

  chart.data.datasets[0].borderColor = lineColor;
  chart.data.datasets[0].backgroundColor = hexToRgba(lineColor, 0.1);
  chart.options.plugins.legend.labels.color = textColor;
  for (const axis of [chart.options.scales.x, chart.options.scales.y]) {
    axis.ticks.color = textColor;
    axis.grid.color = gridColor;
  }
  chart.update('none');
}

// editor.js 와 같은 방식으로 테마 변경을 감시해 축·그리드·범례 색을 갱신한다.
// 색만 갱신한다 — loadTierChart() 를 다시 부르면 색을 바꾸려고 /api/tier-history 를
// 재요청하고(editor.js 는 setOption 만 한다), 통계 탭이 비활성일 때는 0×0 canvas 에
// 차트를 재생성한다.
new MutationObserver(recolorTierChart)
  .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
