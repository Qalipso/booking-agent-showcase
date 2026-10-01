/**
 * Страницы по ссылке из уведомления: оценка визита, освободившееся место,
 * свои записи. Одна страница на три адреса — что показать, решает `pathname`.
 *
 * Язык берём из ссылки, затем из языка телефона клиента: салон в Монтевидео
 * пишет клиентам по-испански, и русская страница по ссылке из испанского
 * сообщения выглядит ошибкой, а не заботой.
 */
(function () {
  const [, kind, id] = location.pathname.split('/');
  const params = new URLSearchParams(location.search);
  const TOKEN = params.get('token') || '';
  const TENANT = params.get('tenant') || '';

  // ---- языки ---------------------------------------------------------------
  const DICT = {
    ru: {
      loading: 'Загружаем…', offline: 'Не удалось связаться с салоном. Попробуйте позже.',
      badLink: 'Ссылка недействительна или устарела.',
      writeWa: 'Написать в WhatsApp',
      // отзыв
      reviewTitle: 'Как прошёл визит?',
      reviewLead: 'Поставьте оценку — это займёт несколько секунд.',
      reviewPh5: 'Пара слов о визите — по желанию',
      reviewPhLow: 'Что стоит улучшить? Это увидит только владелец салона',
      send: 'Отправить', sending: 'Отправляем…',
      thanks: 'Спасибо за оценку!',
      thanksPublic: 'Спасибо! Если не сложно, повторите пару слов на карте — это очень помогает салону.',
      thanksPrivate: 'Спасибо, что написали. Владелец салона прочитает это лично.',
      toMaps: 'Оставить отзыв в Google',
      // лист ожидания
      waitTitle: 'Освободилось место',
      waitLead: '{service} — {when}. Предложение действует {left} и достанется первому, кто подтвердит.',
      waitLeadPlain: 'Предложение действует {left} и достанется первому, кто подтвердит.',
      take: 'Забрать место', taking: 'Записываем…',
      waitGone: 'Это предложение уже неактуально — место занял кто-то другой.',
      waitDone: 'Готово, вы записаны!',
      minutes: '{n} мин', hoursLeft: '{h} ч {n} мин',
      // мои записи
      myTitle: 'Ваши записи', myHi: '{name}, вот ваши будущие визиты.',
      myEmpty: 'Будущих записей нет.',
      confirmed: 'Визит подтверждён', confirm: 'Подтверждаю визит',
      reschedule: 'Перенести', cancel: 'Отменить',
      cancelSure: 'Точно отменить эту запись?', cancelYes: 'Да, отменить', keep: 'Оставить',
      cancelled: 'Запись отменена.',
      pickDay: 'На какой день перенести?', pickTime: 'Свободное время {date}:',
      noSlots: 'На этот день свободных окон нет.',
      errSlotTaken: 'Это время только что заняли. Выберите, пожалуйста, другое.',
      errCalendarDown: 'Не получилось подтвердить прямо сейчас. Напишите нам в WhatsApp.',
      back: '← Назад', moved: 'Перенесли — до встречи!',
      withMaster: '{service} · {master}',
    },
    es: {
      loading: 'Cargando…', offline: 'No pudimos conectar con el salón. Inténtelo más tarde.',
      badLink: 'El enlace no es válido o ya expiró.',
      writeWa: 'Escribir por WhatsApp',
      reviewTitle: '¿Cómo estuvo su visita?',
      reviewLead: 'Déjenos su puntuación — toma unos segundos.',
      reviewPh5: 'Unas palabras sobre la visita — opcional',
      reviewPhLow: '¿Qué podemos mejorar? Solo lo verá el dueño del salón',
      send: 'Enviar', sending: 'Enviando…',
      thanks: '¡Gracias por su puntuación!',
      thanksPublic: '¡Gracias! Si puede, repita esas palabras en el mapa — al salón le ayuda muchísimo.',
      thanksPrivate: 'Gracias por escribirnos. El dueño del salón lo leerá personalmente.',
      toMaps: 'Dejar reseña en Google',
      waitTitle: 'Se liberó un lugar',
      waitLead: '{service} — {when}. La oferta vale {left} y será para quien confirme primero.',
      waitLeadPlain: 'La oferta vale {left} y será para quien confirme primero.',
      take: 'Tomar el lugar', taking: 'Reservando…',
      waitGone: 'Esta oferta ya no está disponible — alguien tomó el lugar.',
      waitDone: '¡Listo, su reserva está confirmada!',
      minutes: '{n} min', hoursLeft: '{h} h {n} min',
      myTitle: 'Sus reservas', myHi: '{name}, estas son sus próximas visitas.',
      myEmpty: 'No hay visitas próximas.',
      confirmed: 'Visita confirmada', confirm: 'Confirmo la visita',
      reschedule: 'Cambiar', cancel: 'Cancelar',
      cancelSure: '¿Seguro que desea cancelar esta reserva?', cancelYes: 'Sí, cancelar', keep: 'Mantener',
      cancelled: 'Reserva cancelada.',
      pickDay: '¿Para qué día?', pickTime: 'Horarios libres el {date}:',
      noSlots: 'Ese día no queda ningún hueco.',
      errSlotTaken: 'Acaban de reservar ese horario. Elija otro, por favor.',
      errCalendarDown: 'No pude confirmarlo en este momento. Escríbanos por WhatsApp.',
      back: '← Atrás', moved: '¡Cambiado, nos vemos!',
      withMaster: '{service} · {master}',
    },
    en: {
      loading: 'Loading…', offline: 'We could not reach the salon. Please try again later.',
      badLink: 'This link is invalid or has expired.',
      writeWa: 'Message on WhatsApp',
      reviewTitle: 'How was your visit?',
      reviewLead: 'Leave a rating — it takes a few seconds.',
      reviewPh5: 'A few words about the visit — optional',
      reviewPhLow: 'What could be better? Only the salon owner will see this',
      send: 'Send', sending: 'Sending…',
      thanks: 'Thank you for the rating!',
      thanksPublic: 'Thank you! If you can, repeat those words on the map — it helps the salon a lot.',
      thanksPrivate: 'Thank you for writing. The salon owner will read this personally.',
      toMaps: 'Leave a Google review',
      waitTitle: 'A slot opened up',
      waitLead: '{service} — {when}. The offer is valid for {left} and goes to whoever confirms first.',
      waitLeadPlain: 'The offer is valid for {left} and goes to whoever confirms first.',
      take: 'Take the slot', taking: 'Booking…',
      waitGone: 'This offer is no longer available — someone else took the slot.',
      waitDone: 'Done, you are booked!',
      minutes: '{n} min', hoursLeft: '{h} h {n} min',
      myTitle: 'Your bookings', myHi: '{name}, here are your upcoming visits.',
      myEmpty: 'No upcoming visits.',
      confirmed: 'Visit confirmed', confirm: 'I confirm the visit',
      reschedule: 'Reschedule', cancel: 'Cancel',
      cancelSure: 'Cancel this booking for sure?', cancelYes: 'Yes, cancel', keep: 'Keep it',
      cancelled: 'Booking cancelled.',
      pickDay: 'Which day should we move it to?', pickTime: 'Free times on {date}:',
      noSlots: 'No free slots that day.',
      errSlotTaken: 'That time has just been taken. Please pick another one.',
      errCalendarDown: 'I could not confirm it right now. Please message us on WhatsApp.',
      back: '← Back', moved: 'Moved — see you soon!',
      withMaster: '{service} · {master}',
    },
  };

  const norm = (code) => (String(code || '').slice(0, 2).toLowerCase() === 'es' ? 'es'
    : String(code || '').slice(0, 2).toLowerCase() === 'en' ? 'en' : 'ru');
  const lang = norm(params.get('lang') || navigator.language || 'ru');
  const LOCALE = { ru: 'ru-RU', es: 'es-UY', en: 'en-GB' }[lang];
  const t = (key, vars) => Object.entries(vars || {})
    .reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), DICT[lang][key] ?? key);

  document.documentElement.lang = lang;

  // ---- каркас --------------------------------------------------------------
  const $ = (s) => document.querySelector(s);
  const view = $('#view');

  const el = (tag, props = {}, ...kids) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (v === null || v === undefined) return;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'html') node.innerHTML = v;
      else if (k.startsWith('on')) node[k] = v;
      else node.setAttribute(k, v);
    });
    kids.filter(Boolean).forEach((k) => node.append(k));
    return node;
  };
  const show = (...nodes) => view.replaceChildren(...nodes.filter(Boolean));

  const withTenant = (path) => path + (path.includes('?') ? '&' : '?')
    + (TENANT ? `tenant=${encodeURIComponent(TENANT)}&` : '') + `lang=${lang}`;
  const signed = (path) => withTenant(path) + `&token=${encodeURIComponent(TOKEN)}`;

  const ERROR_KEYS = { slot_taken: 'errSlotTaken', calendar_down: 'errCalendarDown' };

  async function api(path, options) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // Отказы по подписи и «не найдено» объясняем сами и на языке клиента:
      // серверные тексты всегда русские, а страницу читает испанка.
      // Отказы инструментов приходят с кодом — по нему берём свой перевод:
      // текст сервера написан для модели и всегда русский.
      const key = ERROR_KEYS[data.detail?.code];
      const error = new Error([403, 404].includes(res.status)
        ? t('badLink')
        : (key ? t(key) : (data.detail?.error || data.detail || data.error || t('offline'))));
      error.status = res.status;
      throw error;
    }
    return data;
  }

  const TICK = '<svg viewBox="0 0 52 52" fill="none" stroke="#D97855" stroke-width="2.4" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<circle cx="26" cy="26" r="23"/><path d="M15 27.5 22.5 35 37 18"/></svg>';

  const done = (title, note, extra) => show(
    el('div', { class: 'done' }, el('div', { html: TICK }), el('h1', { text: title }),
      note ? el('p', { class: 'muted', text: note }) : null),
    extra || null,
  );

  // Время без часового пояса означает UTC: так его пишет база, и так же его
  // читает бэкенд. Без этой поправки «15 минут на ответ» превращались в 195 —
  // ровно на разницу с Монтевидео.
  const asDate = (iso) => new Date(/([zZ]|[+-]\d{2}:?\d{2})$/.test(String(iso)) ? iso : `${iso}Z`);

  const fmtWhen = (iso) => asDate(iso).toLocaleString(LOCALE,
    { weekday: 'short', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
  const fmtDay = (iso) => asDate(iso).toLocaleDateString(LOCALE,
    { weekday: 'short', day: 'numeric', month: 'long' });

  // ---- шапка и подвал ------------------------------------------------------
  let cfg = null;

  async function paintSalon() {
    try {
      cfg = await api(withTenant('/api/config'));
    } catch { return; }
    const salon = cfg.salon || {};
    document.title = salon.name || document.title;
    $('#salon').textContent = salon.name || '';
    $('#logo').textContent = (salon.name || 'A').trim().charAt(0).toUpperCase();
    $('#tagline').textContent = salon.tagline || '';
    $('#address').textContent = salon.address || '';
    if (salon.whatsapp) {
      const wa = $('#wa');
      wa.href = salon.whatsapp;
      wa.textContent = t('writeWa');
      wa.className = 'button ghost';
      wa.hidden = false;
    }
  }

  const titleOf = (list, itemId, key) =>
    (cfg?.[list] || []).find((x) => x.id === itemId)?.[key] || itemId;

  // ---- оценка визита -------------------------------------------------------
  function reviewView() {
    let score = 0;
    const comment = el('textarea', { placeholder: t('reviewPh5') });
    const stars = el('div', { class: 'stars', role: 'group', 'aria-label': t('reviewTitle') });
    const send = el('button', { class: 'primary', text: t('send'), disabled: 'disabled' });

    for (let n = 1; n <= 5; n++) {
      const b = el('button', {
        text: '★', 'aria-label': `${n}/5`, 'aria-pressed': 'false',
        onclick: () => {
          score = n;
          [...stars.children].forEach((x, i) => x.setAttribute('aria-pressed', String(i < n)));
          // Довольным предлагаем сказать пару слов, недовольных спрашиваем по делу.
          comment.placeholder = t(n >= 5 ? 'reviewPh5' : 'reviewPhLow');
          send.disabled = false;
          if (n < 5) comment.focus();
        },
      });
      stars.append(b);
    }

    send.onclick = async () => {
      send.disabled = true;
      send.textContent = t('sending');
      try {
        const res = await api(signed(`/api/reviews/${encodeURIComponent(id)}`), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ score, feedback: comment.value.trim() }),
        });
        // Публично зовём только довольных: пятёрка ведёт на карту, остальное
        // уходит владельцу лично — так работает фильтр отзывов.
        const maps = res.googleMaps
          ? el('a', { class: 'button primary', href: res.googleMaps, target: '_blank',
                      rel: 'noopener', text: t('toMaps') })
          : null;
        done(t('thanks'), t(res.public && maps ? 'thanksPublic' : 'thanksPrivate'), maps);
      } catch (e) {
        send.disabled = false;
        send.textContent = t('send');
        show(...view.children, el('p', { class: 'error', text: e.message }));
      }
    };

    show(el('h1', { text: t('reviewTitle') }), el('p', { class: 'muted', text: t('reviewLead') }),
      stars, comment, el('div', { class: 'row' }, send));
  }

  // ---- освободившееся место ------------------------------------------------
  async function waitlistView() {
    let offer;
    try {
      offer = await api(signed(`/api/waitlist/${encodeURIComponent(id)}/offer`));
    } catch (e) {
      return show(el('h1', { text: t('waitTitle') }), el('p', { class: 'error', text: e.message }));
    }
    if (!offer.active) {
      return show(el('h1', { text: t('waitTitle') }), el('p', { class: 'muted', text: t('waitGone') }));
    }

    const mins = Math.max(1, Math.round((asDate(offer.expiresAt) - Date.now()) / 60000));
    const left = mins < 60 ? t('minutes', { n: mins })
      : t('hoursLeft', { h: Math.floor(mins / 60), n: mins % 60 });
    const service = titleOf('services', offer.serviceId, 'title');
    const take = el('button', { class: 'primary', text: t('take') });
    take.onclick = async () => {
      take.disabled = true;
      take.textContent = t('taking');
      try {
        const res = await api(signed(`/api/waitlist/${encodeURIComponent(id)}/accept`), { method: 'POST' });
        done(t('waitDone'), res.booking ? fmtWhen(res.booking.start || offer.start || Date.now()) : '');
      } catch (e) {
        show(el('h1', { text: t('waitTitle') }), el('p', { class: 'error', text: e.message }));
      }
    };

    show(el('h1', { text: t('waitTitle') }),
      el('p', { text: t('waitLeadPlain', { left }) }),
      service ? el('p', { class: 'muted', text: service }) : null,
      el('div', { class: 'row' }, take));
  }

  // ---- мои записи ----------------------------------------------------------
  async function manageView() {
    let data;
    try {
      data = await api(signed(`/api/manage/${encodeURIComponent(id)}`));
    } catch (e) {
      return show(el('h1', { text: t('myTitle') }), el('p', { class: 'error', text: e.message }));
    }

    const list = el('div', { class: 'view', style: 'padding:0;gap:12px' });
    // Ближайший визит первым: порядок в ответе не гарантирован, а клиент читает
    // список сверху и ждёт увидеть там то, что случится раньше.
    [...data.bookings].sort((a, b) => String(a.start).localeCompare(String(b.start)))
      .forEach((b) => list.append(bookingCard(b, manageView)));
    show(el('h1', { text: t('myTitle') }),
      el('p', { class: 'muted', text: data.client?.name ? t('myHi', { name: data.client.name }) : '' }),
      data.bookings.length ? list : el('p', { class: 'muted', text: t('myEmpty') }));
  }

  function bookingCard(b, reload) {
    const card = el('div', { class: 'item' },
      el('span', { class: 'when', text: fmtWhen(b.start) }),
      el('span', {
        class: 'what',
        text: t('withMaster', {
          service: titleOf('services', b.serviceId, 'title'),
          master: titleOf('masters', b.masterId, 'name'),
        }),
      }));

    const actions = el('div', { class: 'row' });
    if (b.confirmed) {
      card.append(el('span', { class: 'badge', text: `✓ ${t('confirmed')}` }));
    } else {
      const ok = el('button', { class: 'primary', text: t('confirm') });
      ok.onclick = async () => {
        ok.disabled = true;
        await api(signed(`/api/manage/${encodeURIComponent(id)}/bookings/${b.id}/confirm`), { method: 'POST' })
          .catch(() => {});
        reload();
      };
      actions.append(ok);
    }

    // Кнопку показываем только там, где действие разрешено политикой салона:
    // предложить перенос и отказать после выбора времени — хуже, чем не
    // предлагать вовсе.
    const allowed = cfg?.actions || {};
    const move = el('button', { class: 'ghost', text: t('reschedule') });
    move.onclick = () => rescheduleView(b, reload);
    const drop = el('button', { class: 'ghost', text: t('cancel') });
    drop.onclick = () => {
      // Подтверждение прямо в карточке: системный confirm() на телефоне
      // выглядит сообщением браузера, а не салона.
      actions.replaceChildren(
        el('span', { class: 'what', text: t('cancelSure') }),
        el('button', {
          class: 'primary', text: t('cancelYes'),
          onclick: async (e) => {
            e.target.disabled = true;
            await api(signed(`/api/manage/${encodeURIComponent(id)}/bookings/${b.id}/cancel`), { method: 'POST' })
              .catch(() => {});
            reload();
          },
        }),
        el('button', { class: 'ghost', text: t('keep'), onclick: reload }),
      );
    };
    if (allowed.reschedule !== false) actions.append(move);
    if (allowed.cancel !== false) actions.append(drop);
    card.append(actions);
    return card;
  }

  // ---- перенос -------------------------------------------------------------
  async function rescheduleView(booking, reload) {
    const back = el('button', { class: 'ghost', text: t('back'), onclick: reload });
    show(el('h1', { text: t('reschedule') }), el('p', { class: 'muted', text: t('pickDay') }),
      el('p', { class: 'muted', text: t('loading') }));

    let days;
    try {
      ({ days } = await api(withTenant(`/api/days?masterId=${encodeURIComponent(booking.masterId)}`)));
    } catch (e) {
      return show(el('h1', { text: t('reschedule') }), el('p', { class: 'error', text: e.message }),
        el('div', { class: 'row' }, back));
    }

    const chips = el('div', { class: 'chips' });
    days.forEach((d) => chips.append(el('button', {
      text: d.label, onclick: () => pickSlot(booking, d, reload),
    })));
    show(el('h1', { text: t('reschedule') }), el('p', { class: 'muted', text: t('pickDay') }),
      chips, el('div', { class: 'row' }, back));
  }

  async function pickSlot(booking, day, reload) {
    const back = el('button', { class: 'ghost', text: t('back'), onclick: () => rescheduleView(booking, reload) });
    let slots;
    try {
      ({ slots } = await api(withTenant(
        `/api/slots?masterId=${encodeURIComponent(booking.masterId)}`
        + `&serviceId=${encodeURIComponent(booking.serviceId)}&date=${day.date}`)));
    } catch (e) {
      return show(el('h1', { text: t('reschedule') }), el('p', { class: 'error', text: e.message }),
        el('div', { class: 'row' }, back));
    }
    if (!slots.length) {
      return show(el('h1', { text: t('reschedule') }), el('p', { class: 'muted', text: t('noSlots') }),
        el('div', { class: 'row' }, back));
    }

    const chips = el('div', { class: 'chips' });
    slots.forEach((s) => chips.append(el('button', {
      text: s.time,
      onclick: async (e) => {
        [...chips.children].forEach((x) => { x.disabled = true; });
        e.target.textContent = t('sending');
        try {
          await api(signed(`/api/manage/${encodeURIComponent(id)}/bookings/${booking.id}/reschedule`), {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ masterId: booking.masterId, start: s.start, slotToken: s.token }),
          });
          done(t('moved'), `${fmtDay(s.start)}, ${s.time}`);
        } catch (err) {
          show(el('h1', { text: t('reschedule') }), el('p', { class: 'error', text: err.message }),
            el('div', { class: 'row' }, back));
        }
      },
    })));
    show(el('h1', { text: t('reschedule') }),
      el('p', { class: 'muted', text: t('pickTime', { date: day.label }) }),
      chips, el('div', { class: 'row' }, back));
  }

  // ---- запуск --------------------------------------------------------------
  (async () => {
    $('#boot').textContent = t('loading');
    await paintSalon();
    if (!TOKEN || !id) return show(el('p', { class: 'error', text: t('badLink') }));
    if (kind === 'review') return reviewView();
    if (kind === 'waitlist') return waitlistView();
    if (kind === 'manage') return manageView();
    show(el('p', { class: 'error', text: t('badLink') }));
  })();
})();
