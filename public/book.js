/**
 * Публичная страница записи: `/book/<код бизнеса>`.
 *
 * Шапку и мета-теги отдаёт сервер — их читают краулеры и превью в WhatsApp,
 * а JS у них не выполняется. Всё остальное (услуги, мастера, часы) страница
 * забирает тем же публичным `/api/config`, что и виджет: два источника правды
 * разошлись бы на первой же правке прайса.
 *
 * Клик по услуге открывает виджет — записывает по-прежнему он один.
 */
(function () {
  const slug = document.body.dataset.tenant || '';
  const params = new URLSearchParams(location.search);

  const DICT = {
    ru: {
      book: 'Записаться онлайн', services: 'Услуги', masters: 'Мастера',
      minutes: '{n} мин', hours: '{days} · {from}–{to}',
      wa: 'WhatsApp', ig: 'Instagram',
      dayShort: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
      offline: 'Не удалось загрузить услуги. Записаться можно кнопкой ниже.',
    },
    es: {
      book: 'Reservar en línea', services: 'Servicios', masters: 'Profesionales',
      minutes: '{n} min', hours: '{days} · {from}–{to}',
      wa: 'WhatsApp', ig: 'Instagram',
      dayShort: ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'],
      offline: 'No pudimos cargar los servicios. Puede reservar con el botón de abajo.',
    },
    en: {
      book: 'Book online', services: 'Services', masters: 'Specialists',
      minutes: '{n} min', hours: '{days} · {from}–{to}',
      wa: 'WhatsApp', ig: 'Instagram',
      dayShort: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      offline: 'Could not load the services. You can still book with the button below.',
    },
  };

  const norm = (code) => {
    const two = String(code || '').slice(0, 2).toLowerCase();
    return two === 'es' ? 'es' : two === 'en' ? 'en' : 'ru';
  };
  const lang = norm(params.get('lang') || document.documentElement.lang || navigator.language);
  const t = (key, vars) => Object.entries(vars || {})
    .reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), DICT[lang][key] ?? key);

  const el = (tag, props = {}, ...kids) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (v === null || v === undefined) return;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k.startsWith('on')) node[k] = v;
      else node.setAttribute(k, v);
    });
    kids.filter(Boolean).forEach((k) => node.append(k));
    return node;
  };

  /** «Пн–Сб» из списка рабочих дней: подряд идущие дни сворачиваем в диапазон. */
  function workDaysLabel(days) {
    const names = DICT[lang].dayShort;
    const list = [...new Set((days || []).map(Number))].sort((a, b) => ((a + 6) % 7) - ((b + 6) % 7));
    if (!list.length) return '';
    const parts = [];
    let from = list[0], prev = list[0];
    const next = (d) => (d + 1) % 7;
    list.slice(1).forEach((d) => {
      if (d === next(prev)) { prev = d; return; }
      parts.push(from === prev ? names[from] : `${names[from]}–${names[prev]}`);
      from = prev = d;
    });
    parts.push(from === prev ? names[from] : `${names[from]}–${names[prev]}`);
    return parts.join(', ');
  }

  const openWidget = () => window.BookingShowcase?.open();

  async function draw() {
    const wrap = document.querySelector('#content');
    let cfg;
    try {
      cfg = await (await fetch(`/api/config?tenant=${encodeURIComponent(slug)}&lang=${lang}`)).json();
    } catch {
      wrap.append(el('p', { class: 'tagline', text: t('offline') }));
      return;
    }

    const salon = cfg.salon || {};
    const hours = salon.workHours;
    if (hours?.start && hours?.end) {
      document.querySelector('#facts').append(el('span', {
        text: t('hours', { days: workDaysLabel(salon.workDays), from: hours.start, to: hours.end }),
      }));
    }
    if (salon.address) document.querySelector('#facts').append(el('span', { text: salon.address }));

    if (cfg.services?.length) {
      const list = el('div', { class: 'services' });
      cfg.services.forEach((s) => list.append(el('button', {
        class: 'service', type: 'button', onclick: openWidget,
        'aria-label': `${t('book')}: ${s.title}`,
      },
        el('span', {},
          el('span', { class: 'name', text: s.title }),
          s.desc ? el('span', { class: 'desc', text: s.desc }) : null),
        el('span', { class: 'meta' },
          s.price ? el('b', { class: 'price', text: s.price }) : null,
          el('span', { class: 'mins', text: t('minutes', { n: s.duration }) })))));
      wrap.append(el('section', {}, el('h2', { text: t('services') }), list));
    }

    if (cfg.masters?.length) {
      const row = el('div', { class: 'masters' });
      cfg.masters.forEach((m) => row.append(el('div', { class: 'master' },
        el('i', { text: (m.name || '?').trim().charAt(0).toUpperCase() }),
        el('span', {}, el('b', { text: m.name }), m.role ? el('small', { text: m.role }) : null))));
      wrap.append(el('section', {}, el('h2', { text: t('masters') }), row));
    }

    const links = el('div', { class: 'links' });
    if (salon.whatsapp) links.append(el('a', { href: salon.whatsapp, target: '_blank', rel: 'noopener', text: t('wa') }));
    if (salon.instagram) links.append(el('a', { href: salon.instagram, target: '_blank', rel: 'noopener', text: t('ig') }));
    wrap.append(el('footer', {}, links, el('small', { text: salon.address || '' })));
  }

  document.querySelector('#cta').textContent = t('book');
  document.querySelector('#cta').onclick = openWidget;
  draw();
})();
