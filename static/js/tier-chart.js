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

let tierChartInstance = null;

async function loadTierChart() {
  if (tierChartInstance) {
    tierChartInstance.destroy();
    tierChartInstance = null;
  }
  try {
    const res = await fetch('/api/tier-history');
    const data = await res.json();
    const history = data.history || [];

    if (!history.length) {
      document.getElementById('tier-chart').classList.add('hidden');
      document.getElementById('tier-chart-empty').classList.remove('hidden');
      return;
    }

    document.getElementById('tier-chart').classList.remove('hidden');
    document.getElementById('tier-chart-empty').classList.add('hidden');

    const seenPids = new Set();
    const deduped = [];
    [...history].reverse().forEach(r => {
      if (!seenPids.has(r.problem_id)) {
        seenPids.add(r.problem_id);
        deduped.push(r);
      }
    });
    deduped.sort((a, b) => a.created_at.localeCompare(b.created_at));

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

    const isDark = !document.body.classList.contains('light');
    const gridColor = isDark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)';
    const textColor = isDark ? '#8892a4' : '#5a6282';

    const tickValues = RATING_TIERS.map(t => t.min);
    const tickLabels = Object.fromEntries(RATING_TIERS.map(t => [t.min, t.label]));

    if (typeof Chart === 'undefined') {
      document.getElementById('tier-chart').classList.add('hidden');
      const emptyEl = document.getElementById('tier-chart-empty');
      emptyEl.textContent = '차트 라이브러리를 불러오는 중입니다. 잠시 후 다시 시도해 주세요.';
      emptyEl.classList.remove('hidden');
      return;
    }

    const ctx = document.getElementById('tier-chart').getContext('2d');
    tierChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: '내 레이팅',
          data: myTierLine,
          borderColor: '#4ecca3',
          backgroundColor: 'rgba(78,204,163,0.08)',
          borderWidth: 2.5,
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
              scale.ticks = tickValues
                .filter(v => v <= scale.max + 20)
                .map(v => ({ value: v }));
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
    console.error('tier chart error', e);
  }
}
