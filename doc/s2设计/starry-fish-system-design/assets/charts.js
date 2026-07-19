(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: Systems Comparison ---
  var chartEl = document.getElementById('chart-systems');
  if (!chartEl) return;
  var chart = echarts.init(chartEl, null, { renderer: 'svg' });

  var categories = [
    'S2入场券\n(努力值)',
    '55星辰木框\n(奇迹)',
    '55猫框\n(星空木框)'
  ];

  chart.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: { type: 'shadow' }
    },
    legend: {
      data: ['平均天数', '中位数', '99分位'],
      bottom: 0,
      textStyle: { color: ink, fontSize: 12 }
    },
    grid: { left: '3%', right: '8%', bottom: '12%', top: '5%', containLabel: true },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: { color: muted, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: '天数',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLabel: { color: muted },
      axisLine: { lineStyle: { color: rule } },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [
      {
        name: '平均天数',
        type: 'bar',
        barWidth: '22%',
        data: [
          { value: 91.6, itemStyle: { color: accent } },
          { value: 105, itemStyle: { color: accent } },
          { value: 20.0, itemStyle: { color: accent } }
        ],
        label: {
          show: true,
          position: 'top',
          color: accent,
          fontSize: 11,
          formatter: '{c}天'
        }
      },
      {
        name: '中位数',
        type: 'bar',
        barWidth: '22%',
        data: [
          { value: 91.0, itemStyle: { color: accent2 } },
          { value: 105, itemStyle: { color: accent2 } },
          { value: 20.0, itemStyle: { color: accent2 } }
        ],
        label: {
          show: true,
          position: 'top',
          color: accent2,
          fontSize: 11,
          formatter: '{c}天'
        }
      },
      {
        name: '99分位',
        type: 'bar',
        barWidth: '22%',
        data: [
          { value: 104, itemStyle: { color: muted } },
          { value: 115, itemStyle: { color: muted } },
          { value: 30, itemStyle: { color: muted } }
        ],
        label: {
          show: true,
          position: 'top',
          color: muted,
          fontSize: 11,
          formatter: '{c}天'
        }
      }
    ]
  });

  window.addEventListener('resize', function() { chart.resize(); });
})();
