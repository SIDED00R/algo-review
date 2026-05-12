// 커스텀 레이팅: 상위 20% 평균 티어 × 60 + 풀이량 보너스(최대 400)
// base   = avg(top floor(N*0.2) tier values) * 60  → max 1800
// volume = round(400 * (1 - 0.99^N))               → max 400  (N≈460 수렴)
// rating = base + volume

const RATING_TIERS = [
  { min: 2100, label: 'Master' },
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

    // 내림차순 정렬 유지 — 상위 20% 평균 계산용
    const tiersSorted = [];
    const myTierLine = [];

    for (const d of uniqueDates) {
      for (const r of byDate[d]) {
        let lo = 0, hi = tiersSorted.length;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (tiersSorted[mid] >= r.tier) lo = mid + 1;
          else hi = mid;
        }
        tiersSorted.splice(lo, 0, r.tier);
      }

      const N = tiersSorted.length;
      const topN = Math.max(1, Math.floor(N * 0.2));
      const topSlice = tiersSorted.slice(0, topN);
      const avgTop = topSlice.reduce((s, v) => s + v, 0) / topN;

      const base = avgTop * 60;
      const volume = Math.round(400 * (1 - Math.pow(0.99, N)));
      myTierLine.push({ x: d, y: Math.round(base + volume) });
    }

    const maxScore = myTierLine.length ? myTierLine[myTierLine.length - 1].y : 50;
    const yMax = Math.max(maxScore * 1.2, 50);

    const isDark = !document.body.classList.contains('light');
    const gridColor = isDark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)';
    const textColor = isDark ? '#8892a4' : '#5a6282';

    const tickValues = RATING_TIERS.map(t => t.min);
    const tickLabels = Object.fromEntries(RATING_TIERS.map(t => [t.min, t.label]));

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
