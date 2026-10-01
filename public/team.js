/* Кабинет мастера: свои записи и свой график.
   Без сборщика и без фреймворка — файл подключается тегом <script> как есть,
   как виджет и панель. Разметка собирается функцией el() через DOM API:
   имя клиента и его комментарий приходят из чужих рук, и innerHTML здесь
   означал бы чужой скрипт на экране мастера. */

const DOW = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const MONTHS_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

const state = {
  tab: 'agenda',      // agenda | schedule
  span: 'day',        // day | week | month
  date: '',           // выбранный день (ключ YYYY-MM-DD)
  month: '',          // месяц графика (YYYY-MM)
  me: null,           // ответ /state: имя, салон, сегодня
  busy: false,
};

const app = () => document.getElementById('app');

/* ---------- мелочи ---------- */

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([key, value]) => {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'on') Object.entries(value).forEach(([ev, fn]) => node.addEventListener(ev, fn));
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value);
  });
  children.flat().filter(Boolean).forEach((child) => node.append(child));
  return node;
}

function toast(text, bad = false) {
  document.querySelectorAll('.toast').forEach((t) => t.remove());
  const node = el('div', { class: bad ? 'toast bad' : 'toast', text, role: 'status' });
  document.body.append(node);
  setTimeout(() => node.remove(), bad ? 5000 : 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...options,
  });
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (!res.ok) {
    // Сессия кончилась — не показываем пустой экран, а честно просим ссылку.
    if (res.status === 401 && state.me) { state.me = null; drawGate('Кабинет закрылся. Откройте свою ссылку заново.'); }
    const detail = body && body.detail;
    const error = new Error(typeof detail === 'string' ? detail
      : (detail && detail.error) || `Ошибка ${res.status}`);
    error.status = res.status;
    error.detail = detail;
    throw error;
  }
  return body;
}

/* ---------- даты ---------- */

function toKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function fromKey(key) {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function shiftDays(key, days) {
  const date = fromKey(key);
  date.setDate(date.getDate() + days);
  return toKey(date);
}

function shiftMonths(key, months) {
  const date = fromKey(`${key}-01`.slice(0, 10));
  date.setMonth(date.getMonth() + months);
  return toKey(date).slice(0, 7);
}

function dayTitle(key, today, short = false) {
  const date = fromKey(key);
  const base = `${date.getDate()} ${(short ? MONTHS_SHORT : MONTHS)[date.getMonth()]}`;
  if (key === today) return `Сегодня, ${base}`;
  if (key === shiftDays(today, 1)) return `Завтра, ${base}`;
  return `${DOW[(date.getDay() + 6) % 7]}, ${base}`;
}

function periodLabel() {
  const today = (state.me && state.me.today) || state.date;
  if (state.span === 'day') return { top: dayTitle(state.date, today, true), sub: '' };
  if (state.span === 'week') {
    const start = shiftDays(state.date, -((fromKey(state.date).getDay() + 6) % 7));
    const end = shiftDays(start, 6);
    const a = fromKey(start);
    const b = fromKey(end);
    const left = a.getMonth() === b.getMonth() ? String(a.getDate()) : `${a.getDate()} ${MONTHS[a.getMonth()]}`;
    return { top: `${left} — ${b.getDate()} ${MONTHS[b.getMonth()]}`, sub: 'неделя' };
  }
  const date = fromKey(state.date);
  return { top: `${MONTHS_NOM[date.getMonth()]} ${date.getFullYear()}`, sub: '' };
}

function plural(count, one, few, many) {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

function money(amount, currency) {
  if (!amount) return '';
  return `${Math.round(amount).toLocaleString('ru-RU')} ${currency || ''}`.trim();
}

/* ---------- вход ---------- */

function drawGate(message) {
  app().replaceChildren(el('div', { class: 'gate' },
    el('div', { class: 'panel' },
      el('h1', { text: 'Кабинет мастера' }),
      el('p', { text: message }))));
  const tabs = document.getElementById('tabs');
  const top = document.getElementById('top');
  if (tabs) tabs.hidden = true;
  if (top) top.hidden = true;
}

async function boot() {
  // Иначе браузер возвращает страницу на прежнее место уже после того, как мы
  // прокрутили её к сегодняшнему дню, — и неделя открывалась на понедельнике.
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  const key = (location.hash.match(/^#k=(.+)$/) || [])[1];
  if (key) {
    // Ключ из адреса убираем сразу: ссылку открывают при людях, и она
    // не должна оставаться на экране и в истории браузера.
    history.replaceState(null, '', location.pathname);
    drawPinScreen(decodeURIComponent(key));
    return;
  }
  let info = null;
  try { info = await api('/api/team/state'); } catch (err) { info = null; }
  if (!info || !info.authenticated) {
    drawGate('Откройте личную ссылку, которую прислал салон, и наберите свой ПИН — четыре цифры.');
    return;
  }
  state.me = info;
  start();
}

/** Кабинет открыт: рисуем шапку, вкладки и первый экран. */
function start() {
  state.date = state.me.today;
  state.month = state.me.today.slice(0, 7);
  drawShell();
  render();
}

/** Второй шаг входа: ссылка есть, нужны четыре цифры.

    Отдельный экран, а не поле в общем интерфейсе: мастер открывает ссылку из
    переписки, и первое, что он должен увидеть, — куда попал и что от него
    хотят. Первый раз просим придумать ПИН, дальше — ввести его. */
async function drawPinScreen(key, message = '', known = null) {
  const top = document.getElementById('top');
  const tabs = document.getElementById('tabs');
  if (top) top.hidden = true;
  if (tabs) tabs.hidden = true;

  let info = known;
  if (!info) {
    app().replaceChildren(el('div', { class: 'gate' },
      el('div', { class: 'panel' }, el('p', { class: 'sub', text: 'Открываем…' }))));
    try {
      info = await api('/api/team/start', { method: 'POST', body: JSON.stringify({ key }) });
    } catch (err) {
      drawGate(err.message);
      return;
    }
  }

  const setup = info.stage === 'setup';
  const pin = pinField('pin', setup ? 'Придумайте ПИН' : 'ПИН');
  const again = setup ? pinField('again', 'Повторите') : null;
  const note = el('p', { class: message ? 'warn' : 'sub' },
    message || (setup
      ? 'Придумайте четыре цифры — их не знает даже салон. Понадобятся при входе с нового телефона.'
      : 'Четыре цифры, которые вы придумали'));
  const go = el('button', { class: 'btn', type: 'button', text: setup ? 'Сохранить и войти' : 'Войти' });

  const fields = [pin, again].filter(Boolean);
  const value = (box) => box.querySelector('input').value;
  const ready = () => fields.every((box) => value(box).length === 4);

  const submit = async () => {
    if (!ready() || go.disabled) return;
    if (setup && value(pin) !== value(again)) {
      drawPinScreen(key, 'Цифры не совпали — наберите ещё раз', info);
      return;
    }
    go.disabled = true;
    fields.forEach((box) => { box.querySelector('input').disabled = true; });
    try {
      state.me = await api('/api/team/enter', {
        method: 'POST', body: JSON.stringify({ key, pin: value(pin) }),
      });
      start();
    } catch (err) {
      // Ключ живёт только в памяти этого экрана: перерисовываем его же, чтобы
      // мастер набрал цифры заново, не открывая ссылку повторно.
      drawPinScreen(key, err.message, info);
    }
  };

  fields.forEach((box, index) => {
    const input = box.querySelector('input');
    input.addEventListener('input', () => {
      input.value = input.value.replace(/\D/g, '').slice(0, 4);
      go.disabled = !ready();
      const next = fields[index + 1];
      if (input.value.length === 4 && next) next.querySelector('input').focus();
      else if (ready()) submit();
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  });
  go.disabled = true;
  go.addEventListener('click', submit);

  app().replaceChildren(el('div', { class: 'gate' },
    el('div', { class: 'panel' },
      el('h1', { text: info.master ? `Здравствуйте, ${info.master}` : 'Кабинет мастера' }),
      el('p', { class: 'salon', text: info.salon || '' }),
      note,
      ...fields,
      go)));
  setTimeout(() => pin.querySelector('input').focus(), 50);
}

/** Поле на четыре цифры с подписью. */
function pinField(id, label) {
  return el('label', { class: 'pin-box' },
    el('span', { text: label }),
    el('input', {
      class: 'pin', id, type: 'text', inputmode: 'numeric', autocomplete: 'off',
      maxlength: '4', pattern: '[0-9]*', placeholder: '••••', 'aria-label': label,
    }));
}


function drawShell() {
  const me = state.me;
  const top = document.getElementById('top');
  top.hidden = false;
  top.replaceChildren(el('div', { class: 'wrap' },
    el('div', { class: 'avatar', 'aria-hidden': 'true', text: (me.master || 'M').trim()[0].toUpperCase() }),
    el('div', { class: 'who' },
      el('b', { text: me.master }),
      el('small', { text: me.salon || '' })),
    el('button', { class: 'exit', type: 'button', text: 'Выйти', on: { click: leave } })));

  const tabs = document.getElementById('tabs');
  tabs.hidden = false;
  tabs.replaceChildren(...[
    ['agenda', '📋', 'Записи'],
    ['schedule', '🗓', 'График'],
  ].map(([id, icon, label]) => el('button', {
    type: 'button', 'aria-pressed': String(state.tab === id),
    on: { click: () => { state.tab = id; render(); } },
  }, el('b', { text: icon, 'aria-hidden': 'true' }), document.createTextNode(label))));
}

async function leave() {
  await api('/api/team/logout', { method: 'POST' }).catch(() => null);
  state.me = null;
  drawGate('Вы вышли. Чтобы вернуться, откройте свою ссылку.');
}

/* ---------- общий каркас экрана ---------- */

function render() {
  const tabs = document.getElementById('tabs');
  Array.from(tabs.children).forEach((btn, i) => {
    btn.setAttribute('aria-pressed', String(state.tab === ['agenda', 'schedule'][i]));
  });
  if (state.tab === 'agenda') drawAgenda();
  else drawSchedule();
}

function navBar(onPrev, onNext, onToday) {
  const label = periodLabel();
  return el('div', { class: 'nav' },
    el('button', { class: 'arrow', type: 'button', 'aria-label': 'Назад', text: '‹', on: { click: onPrev } }),
    el('div', { class: 'label' }, el('span', { text: label.top }),
      label.sub ? el('small', { text: label.sub }) : null),
    onToday ? el('button', { class: 'today', type: 'button', text: 'Сегодня', on: { click: onToday } }) : null,
    el('button', { class: 'arrow', type: 'button', 'aria-label': 'Вперёд', text: '›', on: { click: onNext } }));
}

function skeletons(count) {
  return el('div', {}, ...Array.from({ length: count }, () => el('div', { class: 'skeleton' })));
}

/* ---------- записи ---------- */

async function drawAgenda() {
  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Период' },
    ...[['day', 'День'], ['week', 'Неделя'], ['month', 'Месяц']].map(([id, label]) =>
      el('button', {
        type: 'button', text: label, 'aria-pressed': String(state.span === id),
        on: { click: () => { state.span = id; render(); } },
      })));

  const move = (dir) => {
    if (state.span === 'month') state.date = `${shiftMonths(state.date.slice(0, 7), dir)}-01`;
    else state.date = shiftDays(state.date, dir * (state.span === 'week' ? 7 : 1));
    render();
  };
  const nav = navBar(() => move(-1), () => move(1), () => { state.date = state.me.today; render(); });

  const body = el('div', {}, skeletons(3));
  app().replaceChildren(el('div', { class: 'wrap' }, seg, nav, body));

  let data;
  try {
    data = await api(`/api/team/agenda?span=${state.span}&date=${state.date}`);
  } catch (err) {
    body.replaceChildren(el('p', { class: 'empty', text: err.message }));
    return;
  }
  if (state.span === 'month') fillMonthAgenda(body, data);
  else fillListAgenda(body, data);
}

function fillListAgenda(body, data) {
  const total = data.days.reduce((sum, d) => sum + d.count, 0);
  const amount = data.days.reduce((sum, d) => sum + (d.amount || 0), 0);
  const currency = (data.days.flatMap((d) => d.bookings).find((b) => b.currency) || {}).currency || '';

  const parts = [];
  if (state.span === 'week' || total) {
    parts.push(el('div', { class: 'sum' },
      el('div', {}, el('b', { text: String(total) }),
        el('small', { text: plural(total, 'запись', 'записи', 'записей') })),
      amount ? el('div', {}, el('b', { text: money(amount, currency) }), el('small', { text: 'на сумму' })) : null));
  }
  data.days.forEach((day) => parts.push(dayCard(day, data.today)));
  body.replaceChildren(...parts.filter(Boolean));

  // Неделя начинается с понедельника, а мастер живёт сегодняшним днём: без
  // прокрутки он каждый раз листает мимо прошедших дней.
  const current = body.querySelector(`[data-date="${data.today}"]`);
  if (state.span === 'week' && current) {
    // Таймером, а не requestAnimationFrame: в неактивной вкладке кадры не
    // рисуются вовсе, и прокрутка не срабатывала при возврате к кабинету.
    // Прыжком, а не плавно — плавную отменяет любое касание экрана.
    setTimeout(() => current.scrollIntoView({ block: 'start' }), 0);
  }
}

function dayCard(day, today) {
  const items = [
    ...day.bookings.map((b) => ({ at: b.start, node: bookingRow(b, day.date, today) })),
    ...day.blocks.map((b) => ({ at: b.start, node: breakRow(b, day.date, today) })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const hours = day.works && day.start ? `${day.start}–${day.end}` : '';
  // В режиме «День» дату уже назвала перемотка сверху — второй раз она только
  // отнимает строку на маленьком экране.
  const head = state.span === 'day'
    ? el('h3', {}, document.createTextNode(day.works ? `Работаю ${hours}` : 'Выходной'))
    : el('h3', {}, document.createTextNode(dayTitle(day.date, today)), el('span', { text: hours }));
  const section = el('section', {
    class: day.works ? 'day' : 'day rest',
    'data-date': day.date,
  }, head);

  // Пустой день в неделе — одна строка. Иначе четыре свободных дня подряд
  // занимают весь экран, и до сегодняшних записей приходится листать.
  if (!items.length) {
    section.append(el('p', { class: 'empty', text: day.works ? 'записей нет' : 'выходной' }));
    if (state.span === 'day') section.append(breakButton(day, today));
    return section;
  }

  items.forEach((i) => section.append(i.node));
  section.append(breakButton(day, today));
  return section;
}

function breakButton(day, today) {
  // Перерыв ставится только на сегодня и вперёд: прошедший день уже прошёл.
  if (day.date < today) return null;
  return el('button', {
    class: 'btn ghost', type: 'button', text: '+ перерыв',
    on: { click: () => openBreakSheet(day.date) },
  });
}

function bookingRow(b, date, today) {
  const past = date < today;
  const parts = [
    el('div', { class: 'when' }, el('span', { text: b.start }), el('small', { text: b.end })),
    el('div', { class: 'what' },
      el('b', {}, document.createTextNode(b.service),
        b.groupSize > 1 ? el('span', { class: 'tag', text: `×${b.groupSize}` }) : null,
        b.status === 'cancelled' ? el('span', { class: 'tag', text: 'отменена' }) : null),
      el('div', { class: 'who-line', text: [b.client, money(b.price, b.currency)].filter(Boolean).join(' · ') }),
      b.comment ? el('div', { class: 'note', text: b.comment }) : null),
  ];
  if (b.phone) {
    parts.push(el('a', {
      class: 'call', href: `tel:${b.phone.replace(/[^\d+]/g, '')}`,
      'aria-label': `Позвонить: ${b.client}`, text: '📞',
    }));
  }
  return el('article', { class: past ? 'item done' : 'item' }, ...parts);
}

function breakRow(block, date, today) {
  return el('article', { class: 'item pause' },
    el('div', { class: 'when' }, el('span', { text: block.start }), el('small', { text: block.end })),
    el('div', { class: 'what' }, el('b', { text: block.title || 'Перерыв' })),
    date >= today ? el('button', {
      class: 'call', type: 'button', text: '✕', 'aria-label': 'Убрать перерыв',
      on: { click: () => dropBreak(block.id) },
    }) : null);
}

function fillMonthAgenda(body, data) {
  const today = data.today;
  const grid = el('div', { class: 'grid' },
    ...DOW.map((d) => el('div', { class: 'dow', text: d })));
  const lead = (fromKey(data.days[0].date).getDay() + 6) % 7;
  for (let i = 0; i < lead; i += 1) grid.append(el('div', {}));

  data.days.forEach((day) => {
    const classes = ['cell'];
    if (!day.works) classes.push('rest');
    if (day.date < today) classes.push('past');
    if (day.date === today) classes.push('today');
    grid.append(el('button', {
      class: classes.join(' '), type: 'button',
      'aria-label': `${day.date}: записей ${day.count}`,
      on: { click: () => { state.date = day.date; state.span = 'day'; render(); } },
    },
    el('span', { text: String(fromKey(day.date).getDate()) }),
    day.count ? el('span', { class: 'dot', text: String(day.count) }) : null));
  });

  const total = data.days.reduce((sum, d) => sum + d.count, 0);
  const amount = data.days.reduce((sum, d) => sum + (d.amount || 0), 0);
  const currency = (data.days.flatMap((d) => d.bookings).find((b) => b.currency) || {}).currency || '';
  body.replaceChildren(
    el('div', { class: 'sum' },
      el('div', {}, el('b', { text: String(total) }),
        el('small', { text: `${plural(total, 'запись', 'записи', 'записей')} за месяц` })),
      amount ? el('div', {}, el('b', { text: money(amount, currency) }), el('small', { text: 'на сумму' })) : null),
    grid,
    el('p', { class: 'empty', text: 'Нажмите на день, чтобы посмотреть записи.' }));
}

/* ---------- график ---------- */

async function drawSchedule() {
  const move = (dir) => { state.month = shiftMonths(state.month, dir); drawSchedule(); };
  const date = fromKey(`${state.month}-01`);
  const nav = el('div', { class: 'nav' },
    el('button', { class: 'arrow', type: 'button', 'aria-label': 'Назад', text: '‹', on: { click: () => move(-1) } }),
    el('div', { class: 'label' }, el('span', { text: `${MONTHS_NOM[date.getMonth()]} ${date.getFullYear()}` }),
      el('small', { text: 'мой график' })),
    el('button', { class: 'arrow', type: 'button', 'aria-label': 'Вперёд', text: '›', on: { click: () => move(1) } }));

  const body = el('div', {}, skeletons(2));
  app().replaceChildren(el('div', { class: 'wrap' }, nav, body));

  let data;
  try {
    data = await api(`/api/team/shifts?month=${state.month}`);
  } catch (err) {
    body.replaceChildren(el('p', { class: 'empty', text: err.message }));
    return;
  }
  fillSchedule(body, data);
}

function fillSchedule(body, data) {
  const grid = el('div', { class: 'grid' }, ...DOW.map((d) => el('div', { class: 'dow', text: d })));
  const lead = (fromKey(data.days[0].date).getDay() + 6) % 7;
  for (let i = 0; i < lead; i += 1) grid.append(el('div', {}));

  data.days.forEach((day) => {
    const classes = ['cell'];
    if (!day.works) classes.push(day.source === 'off' ? 'off' : 'rest');
    else if (day.source === 'custom') classes.push('custom');
    if (day.past) classes.push('past');
    if (day.date === data.today) classes.push('today');
    grid.append(el('button', {
      class: classes.join(' '), type: 'button', disabled: day.past || null,
      'aria-label': `${day.date}: ${day.works ? `работаю ${day.start}–${day.end}` : 'выходной'}`,
      on: { click: () => openShiftSheet(day, data) },
    },
    el('span', { text: String(fromKey(day.date).getDate()) }),
    day.works && day.source === 'custom' ? el('span', { class: 'hours', text: day.start }) : null,
    day.bookings ? el('span', { class: 'dot', text: String(day.bookings) }) : null));
  });

  const week = (data.workDays || []).map((d) => DOW[(d + 6) % 7]).join(', ');
  body.replaceChildren(grid,
    el('div', { class: 'legend' },
      el('span', {}, el('i', { style: 'background:rgba(180,85,60,.35)' }), document.createTextNode('выходной')),
      el('span', {}, el('i', { style: 'background:#D97855' }), document.createTextNode('своё время')),
      el('span', {}, el('i', { style: 'background:#D97855;border-radius:50%' }), document.createTextNode('число записей'))),
    el('p', { class: 'empty', text: week ? `Обычно работаю: ${week}. Нажмите на день, чтобы поменять его отдельно — постоянный график меняет владелец.` : '' }));
}

function closeSheet() {
  const sheet = document.querySelector('.sheet');
  if (sheet) sheet.remove();
}

function sheet(title, subtitle, ...content) {
  closeSheet();
  const panel = el('div', { class: 'panel' },
    el('h2', { text: title }),
    el('p', { class: 'sub', text: subtitle }),
    ...content);
  const node = el('div', {
    class: 'sheet', role: 'dialog', 'aria-modal': 'true',
    on: { click: (e) => { if (e.target === node) closeSheet(); } },
  }, panel);
  document.body.append(node);
  return panel;
}

function openShiftSheet(day, month) {
  let mode = day.source === 'week' ? 'default' : (day.source === 'off' ? 'off' : 'work');
  const times = el('div', { class: 'times', hidden: mode !== 'work' ? '' : null },
    el('label', {}, document.createTextNode('Начало'),
      el('input', { type: 'time', id: 'from', value: day.start || month.salonHours.start || '10:00' })),
    el('label', {}, document.createTextNode('Конец'),
      el('input', { type: 'time', id: 'to', value: day.end || month.salonHours.end || '19:00' })));

  const options = [
    ['default', 'Как обычно', 'По моему постоянному графику'],
    ['off', 'Выходной', 'В этот день меня нет'],
    ['work', 'Своё время', 'Работаю не как обычно'],
  ].map(([id, label, hint]) => el('button', {
    class: 'choice', type: 'button', 'aria-pressed': String(mode === id),
    on: {
      click: () => {
        mode = id;
        panel.querySelectorAll('.choice').forEach((b, i) => b.setAttribute('aria-pressed', String(['default', 'off', 'work'][i] === id)));
        if (id === 'work') times.removeAttribute('hidden'); else times.setAttribute('hidden', '');
      },
    },
  }, el('span', {}, el('b', { text: label }), el('small', { text: hint }))));

  const warning = el('p', { class: 'warn', hidden: '' });
  const save = el('button', { class: 'btn', type: 'button', text: 'Сохранить' });
  const panel = sheet(dayTitle(day.date, month.today),
    day.bookings ? `Записей в этот день: ${day.bookings}` : 'Записей пока нет',
    ...options, times, warning,
    el('div', { class: 'row' },
      el('button', { class: 'btn ghost', type: 'button', text: 'Отмена', on: { click: closeSheet } }),
      save));

  let force = false;
  save.addEventListener('click', async () => {
    if (state.busy) return;
    state.busy = true;
    save.disabled = true;
    const payload = {
      date: day.date, mode, force,
      start: mode === 'work' ? panel.querySelector('#from').value : '',
      end: mode === 'work' ? panel.querySelector('#to').value : '',
    };
    try {
      await api('/api/team/shifts', { method: 'PUT', body: JSON.stringify(payload) });
      closeSheet();
      toast('График обновлён');
      drawSchedule();
    } catch (err) {
      if (err.status === 409 && !force) {
        // Записи никуда не денутся от выходного — предупреждаем и спрашиваем ещё раз.
        force = true;
        warning.textContent = `На этот день уже есть записи (${(err.detail && err.detail.bookings) || ''}). Их придётся перенести — салон увидит изменение. Нажмите ещё раз, чтобы закрыть день.`;
        warning.removeAttribute('hidden');
        save.textContent = 'Всё равно закрыть день';
      } else {
        toast(err.message, true);
      }
    } finally {
      state.busy = false;
      save.disabled = false;
    }
  });
}

function openBreakSheet(date) {
  const save = el('button', { class: 'btn', type: 'button', text: 'Поставить' });
  const panel = sheet('Перерыв', `${dayTitle(date, state.me.today)} — время, когда меня нельзя записать`,
    el('div', { class: 'times' },
      el('label', {}, document.createTextNode('С'), el('input', { type: 'time', id: 'bfrom', value: '13:00' })),
      el('label', {}, document.createTextNode('До'), el('input', { type: 'time', id: 'bto', value: '14:00' }))),
    el('div', { class: 'times' },
      el('label', {}, document.createTextNode('Причина'),
        el('input', { type: 'text', id: 'btitle', value: 'Перерыв', maxlength: '60' }))),
    el('div', { class: 'row' },
      el('button', { class: 'btn ghost', type: 'button', text: 'Отмена', on: { click: closeSheet } }),
      save));

  save.addEventListener('click', async () => {
    if (state.busy) return;
    state.busy = true;
    save.disabled = true;
    try {
      const res = await api('/api/team/breaks', {
        method: 'POST',
        body: JSON.stringify({
          date,
          start: panel.querySelector('#bfrom').value,
          end: panel.querySelector('#bto').value,
          title: panel.querySelector('#btitle').value,
        }),
      });
      closeSheet();
      toast(res.warning || 'Перерыв поставлен', Boolean(res.warning));
      render();
    } catch (err) {
      toast(err.message, true);
    } finally {
      state.busy = false;
      save.disabled = false;
    }
  });
}

async function dropBreak(id) {
  if (state.busy) return;
  state.busy = true;
  try {
    const res = await api(`/api/team/breaks/${encodeURIComponent(id)}`, { method: 'DELETE' });
    toast(res.warning || 'Перерыв убран', Boolean(res.warning));
    render();
  } catch (err) {
    toast(err.message, true);
  } finally {
    state.busy = false;
  }
}

document.addEventListener('DOMContentLoaded', boot);
