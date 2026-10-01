/* Примитивы интерфейса Demo Salon: иконки, уведомления, диалоги, боковая панель.
 *
 * Отдельный слой, потому что этим пользуются все экраны: тост об ошибке
 * сохранения и подтверждение удаления мастера должны выглядеть одинаково,
 * где бы их ни вызвали.
 *
 * Браузерные alert/confirm/prompt не используются: они блокируют поток,
 * игнорируют оформление и не переводятся.
 */

(() => {
  const D = document;
  const W = window;

  /* ---------- базовое создание элементов ---------- */

  const el = (tag, props = {}, ...kids) => {
    const n = D.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v === null || v === undefined) continue;
      if (k === 'dataset') Object.assign(n.dataset, v);
      else if (k === 'attrs') Object.entries(v).forEach(([a, x]) => x != null && n.setAttribute(a, x));
      else n[k] = v;
    }
    kids.flat().filter((k) => k !== null && k !== undefined && k !== false).forEach((k) => n.append(k));
    return n;
  };

  /* ---------- иконки ----------
     Контуры Lucide, вставленные инлайном: одна иконка — один <svg>, без
     подключения библиотеки ради двух десятков глифов. */

  const PATHS = {
    calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    chat: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/>',
    chart: '<path d="M3 3v18h18M18 17V9M13 17V5M8 17v-3"/>',
    store: '<path d="m2 7 2-4h16l2 4M4 7v13h16V7M4 7h16"/><path d="M9 20v-6h6v6"/>',
    scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>',
    google: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M12 14v4M10 16h4"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5M3 12a9 3 0 0 0 18 0"/>',
    send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    sparkles: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>',
    bell: '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>',
    handoff: '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M16 21h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/><circle cx="12" cy="12" r="3"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.7 8.9a2 2 0 0 1-.6 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.9 1.9 0 0 1 2.5 0C15.5 3.8 18 5 20 5a1 1 0 0 1 1 1z"/>',
    card: '<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>',
    code: '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
    terminal: '<path d="m4 17 6-6-6-6M12 19h8"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    warning: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0"/><path d="M12 9v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    phone: '<path d="M13.8 10.2a11 11 0 0 0 4.6 4.6l1.4-1.4a1.4 1.4 0 0 1 1.5-.3 12 12 0 0 0 2.4.5 1.4 1.4 0 0 1 1.2 1.4v2.2a1.4 1.4 0 0 1-1.5 1.4A17 17 0 0 1 2.4 4.3 1.4 1.4 0 0 1 3.8 2.8H6a1.4 1.4 0 0 1 1.4 1.2c.1.8.3 1.6.5 2.4a1.4 1.4 0 0 1-.3 1.5z"/>',
    more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    chevronLeft: '<path d="m15 18-6-6 6-6"/>',
    chevronRight: '<path d="m9 18 6-6-6-6"/>',
    sortAsc: '<path d="m3 8 4-4 4 4M7 4v16"/>',
    sortDesc: '<path d="m3 16 4 4 4-4M7 20V4"/>',
    sort: '<path d="m3 8 4-4 4 4M3 16l4 4 4-4"/>',
    plus: '<path d="M5 12h14M12 5v14"/>',
    trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.7 4H7.3a2 2 0 0 0-1.8 1.1z"/>',
    external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    filterOff: '<path d="M3 4h18l-7 8v6l-4 2v-8z"/>',
  };

  /** Иконка как inline-SVG. Декоративная по умолчанию — скринридер её пропустит. */
  function icon(name, { size = 16, label = '', cls = '' } = {}) {
    const svg = D.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.8');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('class', `ico ${cls}`.trim());
    if (label) { svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', label); }
    else svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = PATHS[name] ?? PATHS.info;
    return svg;
  }

  /* ---------- уведомления ---------- */

  const toastHost = () => D.querySelector('.toasts')
    ?? D.body.appendChild(el('div', { className: 'toasts', attrs: { 'aria-live': 'polite', 'aria-atomic': 'false' } }));

  const TOAST_ICON = { ok: 'checkCircle', err: 'alert', warn: 'warning', info: 'info' };

  /**
   * Короткое сообщение о результате действия.
   * @param {'ok'|'err'|'warn'|'info'} kind
   */
  function toast(kind, title, detail = '', { timeout = kind === 'err' ? 7000 : 4000 } = {}) {
    const node = el('div', { className: `toast ${kind}`, attrs: { role: kind === 'err' ? 'alert' : 'status' } },
      icon(TOAST_ICON[kind] ?? 'info', { size: 17 }),
      el('div', { className: 'txt' }, el('b', {}, title), detail ? el('span', {}, detail) : null));

    const close = el('button', {
      className: 'btn btn-icon btn-sm', attrs: { 'aria-label': 'Закрыть уведомление' },
    }, icon('x', { size: 14 }));
    close.style.color = 'inherit';
    node.append(close);

    const remove = () => {
      node.classList.remove('in');
      setTimeout(() => node.remove(), 220);
    };
    close.onclick = remove;
    toastHost().append(node);
    requestAnimationFrame(() => node.classList.add('in'));
    if (timeout) setTimeout(remove, timeout);
    return remove;
  }

  /* ---------- модальные окна ---------- */

  /** Ловушка фокуса: пока окно открыто, Tab не должен уводить на фон. */
  function trapFocus(container, onEscape) {
    const selector = 'a[href], button:not(:disabled), input:not(:disabled), select, textarea, [tabindex]:not([tabindex="-1"])';
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); onEscape(); return; }
      if (e.key !== 'Tab') return;
      const items = [...container.querySelectorAll(selector)].filter((n) => n.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && D.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && D.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    D.addEventListener('keydown', onKey);
    return () => D.removeEventListener('keydown', onKey);
  }

  function openModal(build, { danger = false } = {}) {
    const returnTo = D.activeElement;
    const modal = el('div', {
      className: `modal${danger ? ' danger' : ''}`,
      attrs: { role: 'dialog', 'aria-modal': 'true' },
    });
    const scrim = el('div', { className: 'modal-scrim' }, modal);

    let untrap = () => {};
    const close = (result, resolve) => {
      untrap();
      scrim.classList.remove('in');
      setTimeout(() => scrim.remove(), 220);
      returnTo?.focus?.();
      resolve?.(result);
    };

    return new Promise((resolve) => {
      build(modal, (result) => close(result, resolve));
      D.body.append(scrim);
      untrap = trapFocus(scrim, () => close(false, resolve));
      scrim.onclick = (e) => { if (e.target === scrim) close(false, resolve); };
      requestAnimationFrame(() => {
        scrim.classList.add('in');
        modal.querySelector('[data-autofocus]')?.focus();
      });
    });
  }

  /**
   * Подтверждение действия. Опасные действия помечаются danger:
   * красная кнопка и другой значок — чтобы «Удалить» нельзя было нажать на автомате.
   */
  function confirm({ title, message = '', confirmLabel = 'Подтвердить', cancelLabel = 'Отмена', danger = false }) {
    return openModal((modal, close) => {
      const ok = el('button', { className: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, textContent: confirmLabel });
      ok.dataset.autofocus = '';
      ok.onclick = () => close(true);
      const cancel = el('button', { className: 'btn btn-secondary', textContent: cancelLabel });
      cancel.onclick = () => close(false);
      const id = `m-${Math.random().toString(36).slice(2, 8)}`;
      modal.setAttribute('aria-labelledby', id);
      modal.append(
        el('div', { className: 'modal-ico' }, icon(danger ? 'warning' : 'info', { size: 22 })),
        el('h2', { id }, title),
        message ? el('p', { className: 'hint' }, message) : null,
        el('div', { className: 'actions' }, cancel, ok),
      );
    }, { danger });
  }

  /** Ввод строки. Возвращает строку или null, если отменили. */
  function prompt({ title, message = '', label = '', value = '', placeholder = '', confirmLabel = 'Продолжить', required = true }) {
    return openModal((modal, close) => {
      const input = el('input', { type: 'text', value, placeholder });
      input.dataset.autofocus = '';
      const ok = el('button', { className: 'btn btn-primary', textContent: confirmLabel });
      const submit = () => {
        const v = input.value.trim();
        if (required && !v) { input.focus(); return; }
        close(v || null);
      };
      ok.onclick = submit;
      input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } };
      const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
      cancel.onclick = () => close(null);
      const id = `m-${Math.random().toString(36).slice(2, 8)}`;
      modal.setAttribute('aria-labelledby', id);
      modal.append(
        el('h2', { id }, title),
        message ? el('p', { className: 'hint' }, message) : null,
        el('label', { className: 'field' }, label ? el('span', {}, label) : null, input),
        el('div', { className: 'actions' }, cancel, ok),
      );
    });
  }

  /* ---------- боковая панель ---------- */

  /**
   * Панель справа с деталями объекта. Возвращает { close, body, footer },
   * чтобы содержимое можно было наполнять асинхронно.
   */
  function drawer({ title, subtitle = '' }) {
    const returnTo = D.activeElement;
    const body = el('div', { className: 'body' });
    const footer = el('footer');
    const closeBtn = el('button', {
      className: 'btn btn-icon', attrs: { 'aria-label': 'Закрыть панель' },
    }, icon('x', { size: 18 }));

    const id = `d-${Math.random().toString(36).slice(2, 8)}`;
    const panel = el('aside', {
      className: 'drawer', attrs: { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': id },
    },
      el('header', {},
        el('div', { className: 'titles' },
          el('h2', { id }, title),
          subtitle ? el('small', { className: 'hint' }, subtitle) : null),
        closeBtn),
      body, footer);

    const scrim = el('div', { className: 'scrim' });
    let untrap = () => {};
    const close = () => {
      untrap();
      panel.classList.remove('in');
      scrim.classList.remove('in');
      setTimeout(() => { panel.remove(); scrim.remove(); }, 260);
      returnTo?.focus?.();
    };
    closeBtn.onclick = close;
    scrim.onclick = close;

    D.body.append(scrim, panel);
    untrap = trapFocus(panel, close);
    requestAnimationFrame(() => {
      scrim.classList.add('in');
      panel.classList.add('in');
      closeBtn.focus();
    });
    return { close, body, footer, panel };
  }

  /* ---------- выпадающее меню действий ---------- */

  /** Меню «•••» у строки: три постоянные кнопки в каждой строке — это шум. */
  /** Меню действий строки. Живёт в `body`, а не рядом с кнопкой.
   *
   * Внутри таблицы `absolute`-меню обрезалось: у `.table-wrap` стоит
   * `overflow: hidden` ради скруглённых углов, у `.table-scroll` —
   * `overflow-x: auto` ради прокрутки на телефоне. Против обрезания родителем
   * никакой `z-index` не помогает — элемент должен выйти из этого контейнера.
   * Поэтому открытое меню переезжает в `body` и позиционируется `fixed` по
   * координатам кнопки, а на закрытии удаляется: иначе перерисовка таблицы
   * оставляла бы висеть меню от исчезнувшей строки.
   */
  function actionMenu(trigger, items) {
    const menu = el('div', { className: 'menu right floating', attrs: { role: 'menu' } },
      ...items.filter(Boolean).map((it) => {
        const b = el('button', {
          className: `menu-item${it.danger ? ' danger' : ''}`, type: 'button',
          disabled: Boolean(it.disabled), attrs: { role: 'menuitem' },
        }, it.icon ? icon(it.icon, { size: 15 }) : null, el('span', {}, it.label));
        b.onclick = (e) => { e.stopPropagation(); hide(); it.onSelect(); };
        return b;
      }));

    const hide = () => {
      menu.classList.remove('open');
      menu.remove();
      trigger.setAttribute('aria-expanded', 'false');
      D.removeEventListener('click', hide);
      D.removeEventListener('keydown', onKey);
      W.removeEventListener('resize', hide);
      W.removeEventListener('scroll', hide, true);
    };
    const onKey = (e) => { if (e.key === 'Escape') { hide(); trigger.focus(); } };

    const place = () => {
      const r = trigger.getBoundingClientRect();
      // Правый край меню совпадает с правым краем кнопки — как было у `.right`.
      menu.style.right = `${Math.max(8, W.innerWidth - r.right)}px`;
      menu.style.left = 'auto';
      menu.style.top = `${r.bottom + 6}px`;
      // У нижних строк таблицы места снизу нет — раскрываем вверх, иначе меню
      // уезжает за край экрана и до половины пунктов не дотянуться.
      const h = menu.offsetHeight;
      if (r.bottom + 6 + h > W.innerHeight - 8 && r.top - 6 - h > 8) {
        menu.style.top = `${r.top - 6 - h}px`;
      }
    };

    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.onclick = (e) => {
      e.stopPropagation();
      const open = !menu.classList.contains('open');
      D.querySelectorAll('.menu.open').forEach((m) => {
        m.classList.remove('open');
        if (m.classList.contains('floating')) m.remove();
      });
      if (!open) { hide(); return; }
      D.body.append(menu);
      menu.classList.add('open');
      place();
      trigger.setAttribute('aria-expanded', 'true');
      setTimeout(() => {
        D.addEventListener('click', hide);
        D.addEventListener('keydown', onKey);
        W.addEventListener('resize', hide);
        // Прокрутка любого контейнера уводит кнопку — фиксированное меню
        // осталось бы висеть на прежнем месте. Ловим в фазе перехвата.
        W.addEventListener('scroll', hide, true);
      }, 0);
    };
    return el('div', { className: 'picker' }, trigger);
  }

  /* ---------- состояния ---------- */

  const emptyState = (iconName, title, text, action = null) => el('div', { className: 'state' },
    el('div', { className: 'state-ico' }, icon(iconName, { size: 24 })),
    el('b', {}, title),
    text ? el('p', {}, text) : null,
    action);

  const errorState = (title, text, onRetry = null) => {
    const box = el('div', { className: 'state error' },
      el('div', { className: 'state-ico' }, icon('alert', { size: 24 })),
      el('b', {}, title),
      text ? el('p', {}, text) : null);
    if (onRetry) {
      const b = el('button', { className: 'btn btn-secondary' }, icon('refresh', { size: 15 }), 'Повторить');
      b.onclick = onRetry;
      box.append(b);
    }
    return box;
  };

  /** Скелет таблицы: показываем будущую форму содержимого, а не пустой экран. */
  const skeletonTable = (rows = 6, cols = 6) => el('div', { className: 'table-wrap' },
    el('div', { style: 'padding:16px' },
      ...Array.from({ length: rows }, () => el('div', {
        style: `display:grid;grid-template-columns:repeat(${cols},1fr);gap:12px;padding:10px 0`,
      }, ...Array.from({ length: cols }, () => el('span', { className: 'skel skel-row' }))))));

  const skeletonCards = (n = 4) => el('div', { className: 'kpis' },
    ...Array.from({ length: n }, () => el('div', { className: 'kpi' },
      el('span', { className: 'skel skel-line', style: 'width:60%' }),
      el('span', { className: 'skel', style: 'height:30px;margin:6px 0' }),
      el('span', { className: 'skel skel-line', style: 'width:80%' }))));

  window.UI = {
    el, icon, toast, confirm, prompt, drawer, actionMenu,
    emptyState, errorState, skeletonTable, skeletonCards, trapFocus,
  };
})();
