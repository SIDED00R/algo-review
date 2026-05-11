const TIER_LABELS = {
  0:'Unrated',1:'Bronze V',2:'Bronze IV',3:'Bronze III',4:'Bronze II',5:'Bronze I',
  6:'Silver V',7:'Silver IV',8:'Silver III',9:'Silver II',10:'Silver I',
  11:'Gold V',12:'Gold IV',13:'Gold III',14:'Gold II',15:'Gold I',
  16:'Platinum V',17:'Platinum IV',18:'Platinum III',19:'Platinum II',20:'Platinum I',
  21:'Diamond V',22:'Diamond IV',23:'Diamond III',24:'Diamond II',25:'Diamond I',
  26:'Ruby V',27:'Ruby IV',28:'Ruby III',29:'Ruby II',30:'Ruby I',
};

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
    let runningSum = 0, runningCount = 0, maxAvg = 0;
    const myTierLine = [];
    for (const d of uniqueDates) {
      for (const r of byDate[d]) {
        runningSum += r.tier;
        runningCount++;
        const avg = runningSum / runningCount;
        if (avg > maxAvg) maxAvg = avg;
      }
      myTierLine.push({ x: d, y: maxAvg });
    }

    const isDark = !document.body.classList.contains('light');
    const gridColor = isDark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)';
    const textColor = isDark ? '#8892a4' : '#5a6282';

    const ctx = document.getElementById('tier-chart').getContext('2d');
    tierChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label: '내 티어',
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
              label: ctx => `내 티어: ${TIER_LABELS[Math.round(ctx.parsed.y)] || ctx.parsed.y.toFixed(1)}`,
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
            min: 0, max: 30,
            ticks: {
              color: textColor,
              stepSize: 5,
              callback: v => ({ 0:'Unrated',5:'Bronze I',10:'Silver I',15:'Gold I',20:'Platinum I',25:'Diamond I',30:'Ruby I' })[v] || '',
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
