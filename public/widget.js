/**
 * Demo Salon — чат-виджет записи.
 * Встраивание:  <script src="https://ваш-домен/widget.js" data-api="https://ваш-домен"></script>
 * Всё живёт в Shadow DOM, так что стили сайта-хоста не конфликтуют.
 */
(function () {
  const script = document.currentScript;
  const API = (script?.dataset.api || new URL('.', script.src).origin).replace(/\/$/, '');
  // Код бизнеса: из data-tenant, либо из ?tenant= в адресе страницы (удобно для демо).
  const TENANT = script?.dataset.tenant
    || new URLSearchParams(location.search).get('tenant') || '';
  const SOURCE = script?.dataset.source
    || new URLSearchParams(location.search).get('utm_source') || 'web';
  const withTenant = (path) => (TENANT
    ? path + (path.includes('?') ? '&' : '?') + 'tenant=' + encodeURIComponent(TENANT)
    : path);

  // ---- языки --------------------------------------------------------------
  // Виджет говорит на языке страницы, а после первого сообщения — на языке клиента.
  const DICT = {
    ru: {
      fabLabel: 'Записаться онлайн', closeLabel: 'Закрыть окно записи',
      answerPh: 'Введите ответ…', answerLabel: 'Ваш ответ', sendLabel: 'Отправить',
      status: 'Онлайн-запись', sub: 'Подберём услугу, мастера и удобное время',
      subChat: 'Спросите про услуги, цены и время — или просто запишитесь',
      tip: 'Записаться онлайн ✦', hours: '{days} {from}–{to}',
      dayShort: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
      apiDown: 'Сервис записи недоступен',
      offline: 'Не могу связаться с сервисом записи. Напишите нам в WhatsApp 🙏',
      greeting: 'Здравствуйте! Я помогу записаться в {salon}.\nЧто вас интересует?',
      greetingChat: 'Здравствуйте! Я администратор {salon}.\nНапишите, что хотите сделать — подберу время и запишу.',
      chatHint: 'Можно начать с услуги или написать своими словами',
      wantService: 'Хочу записаться: {title}', fromList: 'Выбрать из списка',
      msgPh: 'Ваше сообщение…', writeWa: 'Написать в WhatsApp',
      guidedStart: 'Хорошо, выберем по шагам.',
      pickLocation: 'Выберите филиал', whichLocation: 'В какой филиал хотите записаться?',
      pickGroup: 'Сколько мест?', groupPlaces: '{n} мест',
      pickService: 'Выберите услугу', pickMaster: 'Выберите мастера',
      noMasters: 'На эту услугу сейчас нет свободных мастеров. Напишите в WhatsApp — подберём вариант.',
      whichMaster: '«{title}» — {price}.\nК кому записать?', minutes: '{n} мин',
      serviceItem: '{title} · {n} мин', serviceItemPriced: '{title} · {n} мин · {price}',
      slotHint: '{date} · {n} мин',
      noDays: 'У мастера нет рабочих дней в ближайшие две недели.',
      whichDay: 'На какой день?', nearestDates: 'Ближайшие даты',
      noSlots: 'На этот день свободных окон нет. Выберем другой?', otherDate: '← Другая дата',
      back: '← Назад',
      wishPh: 'Например: мужская стрижка к Sam в субботу в 15:00',
      wishHint: 'Напишите своими словами — или выберите кнопкой',
      greetingFree: 'Здравствуйте! Я помогу записаться в {salon}.\nНапишите, что и когда хотите — например «мужская стрижка к Sam в субботу в 15:00». Или выберите из списка.',
      wishUnclear: 'Не понял, что подобрать. Выберите из списка — или напишите иначе.',
      wishNarrow: 'Уточните, пожалуйста:',
      wishNoMaster: 'Такого мастера на эту услугу нет. Вот кто её делает:',
      wishNoDay: 'На этот день записи нет. Ближайшие даты:',
      wishNoTime: '{time} на {date} занято или уже прошло.',
      wishTaken: '{time} на {date} уже занято. Ближайшее свободное время:',
      wishTakenNone: '{time} на {date} занято, и других свободных окон в этот день нет. Выберем другой день?',
      allTimes: 'Всё свободное время',
      wishPhMaster: 'Или напишите имя мастера',
      wishPhDay: 'Или напишите день: завтра, в пятницу, 25.09',
      wishPhTime: 'Или напишите своё время, например 16:00',
      liveHint: 'Нашёл по вашим словам — нажмите или Enter',
      liveNearest: 'Это время занято — ближайшее свободное',
      liveGo: 'Продолжить →', liveBook: 'Записаться: {date}, {time}',
      liveFree: '{time} свободно', liveBusy: '{time} занято',
      liveNeed: 'ещё нужно: {list}',
      infoService: 'услуга', infoMaster: 'мастер', infoDay: 'день', infoTime: 'время',
      freeAt: 'Свободное время у {master}:',
      askName: 'Как вас зовут?', namePh: 'Ваше имя',
      askPhone: 'Телефон или WhatsApp для связи?', phonePh: '+598 ...',
      badPhone: 'Похоже, номер неполный. Проверьте, пожалуйста.',
      needCode: 'Если номер не уругвайский, укажите код страны — например +54 9 11 2345 6789.',
      phoneCountryHint: 'Номер другой страны? Выберите код:',
      askComment: 'Есть пожелания к мастеру? Можно пропустить.', commentPh: 'Комментарий', skip: 'Пропустить',
      askPromo: 'Есть промокод?', promoPh: 'Например, HOLA10', noPromo: 'Без промокода',
      askConsent: 'Прислать подтверждение и напоминание о записи в WhatsApp?',
      yesNotify: 'Да, присылайте', noNotify: 'Не нужно',
      summary: 'Проверьте запись:\n\n{service} · {duration}\nМастер: {master}\nКогда: {date}, {time}\nИмя: {name}\nТелефон: {phone}',
      summaryComment: '\nКомментарий: {comment}',
      summaryPromo: '\nПромокод: {promo}',
      summaryGroup: '\nМест: {n}',
      summaryNotify: '\nНапоминания: {value}', notifyOn: 'в WhatsApp', notifyOff: 'не присылать',
      confirmBtn: '✓ Подтвердить', restart: 'Начать заново',
      booked: 'Вы записаны', bookedNote: 'Событие добавлено в календарь мастера. До встречи!',
      manageSent: 'Ссылку на запись — перенести или отменить — пришлём вместе с подтверждением.',
      bookedNoteLocal: 'Записали вас. Администратор подтвердит визит — до встречи!',
      errSlotTaken: 'Это время только что заняли. Выберите, пожалуйста, другое.',
      errGroupFull: 'В этой группе не осталось свободных мест.',
      errGroupOver: 'Столько мест в одной записи нельзя — выберите меньше.',
      errPromoUnknown: 'Такого промокода нет или он больше не действует.',
      errPromoFirst: 'Этот промокод действует только на первый визит.',
      errBadPhone: 'Похоже, номер неполный. Проверьте, пожалуйста.',
      errNeedCountryCode: 'Укажите номер с кодом страны — например +54 9 11 2345 6789.',
      errNeedName: 'Напишите, пожалуйста, ваше имя.',
      errBlocked: 'Онлайн-запись для этого номера отключена. Напишите нам в WhatsApp.',
      errDailyLimit: 'На сегодня по этому номеру уже максимум записей. Напишите нам в WhatsApp.',
      errCalendarDown: 'Не могу подтвердить запись прямо сейчас. Напишите нам в WhatsApp — запишем вручную.',
      sending: 'Отправляю запись…', bookAgain: 'Записаться ещё раз', otherTime: 'Выбрать другое время',
    },
    es: {
      fabLabel: 'Reservar en línea', closeLabel: 'Cerrar la ventana de reserva',
      answerPh: 'Escriba su respuesta…', answerLabel: 'Su respuesta', sendLabel: 'Enviar',
      status: 'Reserva en línea', sub: 'Elegimos servicio, profesional y horario',
      subChat: 'Pregunte por servicios, precios y horarios — o reserve directamente',
      tip: 'Reservar en línea ✦', hours: '{days} {from}–{to}',
      dayShort: ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'],
      apiDown: 'El servicio de reservas no está disponible',
      offline: 'No puedo conectar con el servicio de reservas. Escríbanos por WhatsApp 🙏',
      greeting: '¡Hola! Le ayudo a reservar en {salon}.\n¿Qué le interesa?',
      greetingChat: '¡Hola! Soy el asistente de {salon}.\nEscriba qué necesita — busco el horario y le reservo.',
      chatHint: 'Empiece por un servicio o escríbalo con sus palabras',
      wantService: 'Quiero reservar: {title}', fromList: 'Elegir de la lista',
      msgPh: 'Su mensaje…', writeWa: 'Escribir por WhatsApp',
      guidedStart: 'Perfecto, vamos paso a paso.',
      pickLocation: 'Elija la sucursal', whichLocation: '¿En qué sucursal quiere reservar?',
      pickGroup: '¿Cuántas plazas?', groupPlaces: '{n} plazas',
      pickService: 'Elija el servicio', pickMaster: 'Elija al profesional',
      noMasters: 'Ahora no hay profesionales libres para este servicio. Escríbanos por WhatsApp.',
      whichMaster: '«{title}» — {price}.\n¿Con quién le reservo?', minutes: '{n} min',
      serviceItem: '{title} · {n} min', serviceItemPriced: '{title} · {n} min · {price}', slotHint: '{date} · {n} min',
      noDays: 'El profesional no tiene días laborables en las próximas dos semanas.',
      whichDay: '¿Qué día le viene bien?', nearestDates: 'Próximas fechas',
      noSlots: 'Ese día no queda ningún hueco. ¿Probamos otro?', otherDate: '← Otra fecha',
      back: '← Atrás',
      wishPh: 'Por ejemplo: corte de caballero con Sam el sábado a las 15:00',
      wishHint: 'Escríbalo con sus palabras — o elija con un botón',
      greetingFree: '¡Hola! Le ayudo a reservar en {salon}.\nEscriba qué y cuándo quiere — por ejemplo «corte de caballero con Sam el sábado a las 15:00». O elija de la lista.',
      wishUnclear: 'No entendí qué reservar. Elija de la lista — o escríbalo de otra forma.',
      wishNarrow: 'Precise, por favor:',
      wishNoMaster: 'Ese profesional no hace este servicio. Estos sí:',
      wishNoDay: 'Ese día no hay turnos. Próximas fechas:',
      wishNoTime: 'Las {time} del {date} ya están ocupadas o pasaron.',
      wishTaken: 'Las {time} del {date} ya están ocupadas. Horarios libres más cercanos:',
      wishTakenNone: 'Las {time} del {date} están ocupadas y ese día no quedan otros huecos. ¿Probamos otro día?',
      allTimes: 'Todos los horarios libres',
      wishPhMaster: 'O escriba el nombre del profesional',
      wishPhDay: 'O escriba el día: mañana, el viernes, 25/09',
      wishPhTime: 'O escriba su hora, por ejemplo 16:00',
      liveHint: 'Encontré esto con sus palabras — toque o pulse Enter',
      liveNearest: 'Esa hora está ocupada — la más cercana libre',
      liveGo: 'Continuar →', liveBook: 'Reservar: {date}, {time}',
      liveFree: '{time} libre', liveBusy: '{time} ocupado',
      liveNeed: 'falta: {list}',
      infoService: 'servicio', infoMaster: 'profesional', infoDay: 'día', infoTime: 'hora',
      freeAt: 'Horarios libres de {master}:',
      askName: '¿Cómo se llama?', namePh: 'Su nombre',
      askPhone: '¿Teléfono o WhatsApp de contacto?', phonePh: '+598 ...',
      badPhone: 'El número parece incompleto. Revíselo, por favor.',
      needCode: 'Si el número no es uruguayo, indique el código de país — por ejemplo +54 9 11 2345 6789.',
      phoneCountryHint: '¿Número de otro país? Elija el código:',
      askComment: '¿Alguna preferencia? Puede omitirlo.', commentPh: 'Comentario', skip: 'Omitir',
      askPromo: '¿Tiene un código promocional?', promoPh: 'Por ejemplo, HOLA10', noPromo: 'Sin código',
      askConsent: '¿Le enviamos la confirmación y el recordatorio por WhatsApp?',
      yesNotify: 'Sí, envíenmelo', noNotify: 'No hace falta',
      summary: 'Revise la reserva:\n\n{service} · {duration}\nProfesional: {master}\nCuándo: {date}, {time}\nNombre: {name}\nTeléfono: {phone}',
      summaryComment: '\nComentario: {comment}',
      summaryPromo: '\nCódigo promocional: {promo}',
      summaryGroup: '\nPlazas: {n}',
      summaryNotify: '\nRecordatorios: {value}', notifyOn: 'por WhatsApp', notifyOff: 'no enviar',
      confirmBtn: '✓ Confirmar', restart: 'Empezar de nuevo',
      booked: 'Reserva confirmada', bookedNote: 'El evento se añadió al calendario. ¡Hasta pronto!',
      manageSent: 'Junto con la confirmación le enviamos el enlace para cambiar o cancelar la cita.',
      bookedNoteLocal: 'Reserva registrada. El administrador la confirmará. ¡Hasta pronto!',
      errSlotTaken: 'Acaban de reservar ese horario. Elija otro, por favor.',
      errGroupFull: 'Ya no quedan lugares en ese grupo.',
      errGroupOver: 'No se pueden reservar tantos lugares a la vez — elija menos.',
      errPromoUnknown: 'Ese código promocional no existe o ya no está vigente.',
      errPromoFirst: 'Ese código promocional es solo para la primera visita.',
      errBadPhone: 'El número parece incompleto. Revíselo, por favor.',
      errNeedCountryCode: 'Indique el número con el código de país — por ejemplo +54 9 11 2345 6789.',
      errNeedName: 'Escriba su nombre, por favor.',
      errBlocked: 'La reserva en línea está desactivada para este número. Escríbanos por WhatsApp.',
      errDailyLimit: 'Ya hay demasiadas reservas con este número para hoy. Escríbanos por WhatsApp.',
      errCalendarDown: 'No puedo confirmar la reserva en este momento. Escríbanos por WhatsApp y la hacemos a mano.',
      sending: 'Enviando la reserva…', bookAgain: 'Reservar otra vez', otherTime: 'Elegir otro horario',
    },
    en: {
      fabLabel: 'Book online', closeLabel: 'Close the booking window',
      answerPh: 'Type your answer…', answerLabel: 'Your answer', sendLabel: 'Send',
      status: 'Online booking', sub: 'We will pick the service, specialist and time',
      subChat: 'Ask about services, prices and times — or just book',
      tip: 'Book online ✦', hours: '{days} {from}–{to}',
      dayShort: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      apiDown: 'The booking service is unavailable',
      offline: 'I cannot reach the booking service. Please message us on WhatsApp 🙏',
      greeting: 'Hello! I will help you book at {salon}.\nWhat are you interested in?',
      greetingChat: 'Hello! I am the {salon} assistant.\nTell me what you need — I will find a time and book it.',
      chatHint: 'Start with a service or just write in your own words',
      wantService: 'I would like to book: {title}', fromList: 'Choose from the list',
      msgPh: 'Your message…', writeWa: 'Message on WhatsApp',
      guidedStart: 'Sure, let us go step by step.',
      pickLocation: 'Choose a location', whichLocation: 'Which location would you like to visit?',
      pickGroup: 'How many places?', groupPlaces: '{n} places',
      pickService: 'Choose a service', pickMaster: 'Choose a specialist',
      noMasters: 'No specialist is available for this service right now. Please write to us on WhatsApp.',
      whichMaster: '“{title}” — {price}.\nWho should I book you with?', minutes: '{n} min',
      serviceItem: '{title} · {n} min', serviceItemPriced: '{title} · {n} min · {price}', slotHint: '{date} · {n} min',
      noDays: 'This specialist has no working days in the next two weeks.',
      whichDay: 'Which day works for you?', nearestDates: 'Nearest dates',
      noSlots: 'No free slots that day. Shall we try another?', otherDate: '← Another date',
      back: '← Back',
      wishPh: 'For example: men’s haircut with Sam on Saturday at 15:00',
      wishHint: 'Write it in your own words — or tap a button',
      greetingFree: 'Hello! I will help you book at {salon}.\nWrite what and when you want — for example “men’s haircut with Sam on Saturday at 15:00”. Or pick from the list.',
      wishUnclear: 'I did not catch what to book. Pick from the list — or say it differently.',
      wishNarrow: 'Could you be more precise:',
      wishNoMaster: 'That specialist does not do this service. These do:',
      wishNoDay: 'No slots that day. Nearest dates:',
      wishNoTime: '{time} on {date} is taken or already past.',
      wishTaken: '{time} on {date} is already taken. Nearest free times:',
      wishTakenNone: '{time} on {date} is taken and there are no other free slots that day. Shall we try another day?',
      allTimes: 'All free times',
      wishPhMaster: 'Or type the specialist’s name',
      wishPhDay: 'Or type a day: tomorrow, on Friday, 25.09',
      wishPhTime: 'Or type your own time, e.g. 16:00',
      liveHint: 'Found this from your words — tap or press Enter',
      liveNearest: 'That time is taken — nearest free',
      liveGo: 'Continue →', liveBook: 'Book: {date}, {time}',
      liveFree: '{time} free', liveBusy: '{time} taken',
      liveNeed: 'still needed: {list}',
      infoService: 'service', infoMaster: 'specialist', infoDay: 'day', infoTime: 'time',
      freeAt: 'Free times with {master}:',
      askName: 'What is your name?', namePh: 'Your name',
      askPhone: 'Phone or WhatsApp to reach you?', phonePh: '+598 ...',
      badPhone: 'That number looks incomplete. Please check it.',
      needCode: 'If the number is not Uruguayan, include the country code — for example +1 305 555 0134.',
      phoneCountryHint: 'Number from another country? Pick the code:',
      askComment: 'Any preferences? You can skip this.', commentPh: 'Comment', skip: 'Skip',
      askPromo: 'Do you have a promo code?', promoPh: 'For example, HOLA10', noPromo: 'No promo code',
      askConsent: 'Send the confirmation and a reminder on WhatsApp?',
      yesNotify: 'Yes, please', noNotify: 'No need',
      summary: 'Please check the booking:\n\n{service} · {duration}\nSpecialist: {master}\nWhen: {date}, {time}\nName: {name}\nPhone: {phone}',
      summaryComment: '\nComment: {comment}',
      summaryPromo: '\nPromo code: {promo}',
      summaryGroup: '\nPlaces: {n}',
      summaryNotify: '\nReminders: {value}', notifyOn: 'on WhatsApp', notifyOff: 'do not send',
      confirmBtn: '✓ Confirm', restart: 'Start over',
      booked: 'You are booked', bookedNote: 'The event was added to the calendar. See you soon!',
      manageSent: 'We are sending the link to reschedule or cancel together with the confirmation.',
      bookedNoteLocal: 'Your booking is saved. The manager will confirm it — see you soon!',
      errSlotTaken: 'That time has just been taken. Please pick another one.',
      errGroupFull: 'There are no places left in that group.',
      errGroupOver: 'That many places cannot be booked at once — please pick fewer.',
      errPromoUnknown: 'That promo code does not exist or is no longer valid.',
      errPromoFirst: 'That promo code is for the first visit only.',
      errBadPhone: 'That number looks incomplete. Please check it.',
      errNeedCountryCode: 'Please include the country code — for example +1 305 555 0134.',
      errNeedName: 'Please tell us your name.',
      errBlocked: 'Online booking is disabled for this number. Please message us on WhatsApp.',
      errDailyLimit: 'There are already too many bookings for this number today. Please message us on WhatsApp.',
      errCalendarDown: 'I cannot confirm the booking right now. Message us on WhatsApp and we will book it by hand.',
      sending: 'Sending the booking…', bookAgain: 'Book again', otherTime: 'Pick another time',
    },
  };

  const SUPPORTED = Object.keys(DICT);
  const normLang = (raw) => {
    const code = String(raw || '').trim().toLowerCase().slice(0, 2);
    return SUPPORTED.includes(code) ? code : null;
  };
  const siteLang = () => normLang(document.documentElement.getAttribute('lang'))
    || normLang(document.documentElement.getAttribute('xml:lang'));
  // `?lang=es` в ссылке: салон рассылает её испаноязычным клиентам, и язык
  // страницы для них — не показатель. Раз выбран явно, дальше не меняется.
  const urlLang = () => {
    try { return normLang(new URLSearchParams(location.search).get('lang')); }
    catch { return null; }
  };

  let lang = normLang(script?.dataset.lang) || urlLang() || siteLang()
    || normLang(navigator.language) || 'ru';
  // Пока клиент не написал сам, язык следует за языком страницы.
  let langPinned = Boolean(normLang(script?.dataset.lang) || urlLang());

  const t = (key, vars) => String((DICT[lang] || DICT.ru)[key] ?? DICT.ru[key] ?? key)
    .replace(/\{(\w+)\}/g, (_, k) => (vars && vars[k] != null ? vars[k] : ''));

  /** Язык текста клиента: кириллица → ru, испанские приметы → es, иначе en. */
  function detectLang(text) {
    const s = String(text || '');
    if (/[а-яё]/i.test(s)) return 'ru';
    if (/[áéíóúñ¿¡]/i.test(s)) return 'es';
    const es = /\b(hola|quiero|quisiera|cita|turno|reserva|reservar|corte|color|gracias|por favor|cuanto|cuánto|precio|hoy|mañana|tarde|para)\b/i;
    const en = /\b(hi|hello|i|want|would|like|book|booking|appointment|haircut|price|today|tomorrow|please|thanks)\b/i;
    if (es.test(s)) return 'es';
    if (en.test(s)) return 'en';
    return null;
  }

  /** Подпись рабочих дней: «Пн–Сб» для непрерывной недели, иначе перечислением.
      Салон с выходным не должен читаться в подвале как работающий все семь дней. */
  function workDaysLabel(days) {
    const names = DICT[lang]?.dayShort ?? DICT.ru.dayShort;
    const week = [1, 2, 3, 4, 5, 6, 0];               // неделя начинается с понедельника
    const open = Array.isArray(days) && days.length ? week.filter((d) => days.includes(d)) : week;
    if (!open.length) return '';
    const contiguous = open.every((d, i) => i === 0 || week.indexOf(d) === week.indexOf(open[i - 1]) + 1);
    if (open.length === 1) return names[open[0]];
    return contiguous
      ? `${names[open[0]]}–${names[open[open.length - 1]]}`
      : open.map((d) => names[d]).join(', ');
  }

  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <div class="dock">
      <div class="bubble" role="status" aria-live="polite"></div>
      <button class="fab" aria-expanded="false" aria-haspopup="dialog">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.9 8.9 0 0 1-4-.9L3 20l1.1-4.6A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/>
        </svg>
      </button>
    </div>
    <section class="panel" role="dialog" tabindex="-1" aria-labelledby="am-title" aria-describedby="am-sub">
      <header>
        <button class="back" type="button" hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M14.5 5 8 11.5 14.5 18"/>
          </svg>
        </button>
        <div class="avatar" aria-hidden="true">A</div>
        <div class="ttl">
          <h3 id="am-title">Demo Salon</h3>
          <div class="status"><span class="dot" aria-hidden="true"></span><span class="status-text"></span></div>
          <div class="sub" id="am-sub"></div>
        </div>
        <button class="close">✕</button>
      </header>
      <div class="log" role="log" aria-live="polite" aria-relevant="additions text"></div>
      <div class="choices"></div>
      <div class="wishbar" hidden aria-live="polite"></div>
      <form autocomplete="off"><input type="text"><button type="submit">→</button></form>
      <footer><span class="hours"></span><a href="#" class="wa" target="_blank" rel="noopener">WhatsApp</a></footer>
    </section>`;

  // Стили отдельным файлом с того же домена, что и сам виджет: строгий CSP сайта
  // (style-src без 'unsafe-inline') блокирует инлайновый <style> и replaceSync.
  // Адрес считается от самого widget.js, а не от API: сайт с CSP `style-src 'self'`
  // кладёт виджет рядом с собой, а к API обращается только через connect-src.
  const sheet = document.createElement('link');
  sheet.rel = 'stylesheet';
  sheet.href = new URL('widget.css', script.src).href;
  root.insertBefore(sheet, root.firstChild);

  const $ = (s) => root.querySelector(s);
  const fab = $('.fab'), panel = $('.panel'), log = $('.log'), choices = $('.choices'),
        form = $('form'), input = $('form input'), bubble = $('.bubble'), dock = $('.dock'),
        backBtn = $('.back'), wishbar = $('.wishbar');

  const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => calm.matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));

  const touch = window.matchMedia('(pointer: coarse)');
  const fullscreen = window.matchMedia('(max-width: 460px)');

  /** На телефоне фокус ставит только сам клиент: программный focus() поднимает
      клавиатуру, экран прыгает, а нужная кнопка уезжает из виду. */
  const focusInput = () => { if (!touch.matches) input.focus(); };

  let cfg = null;
  const draft = {};
  let step = 'idle';
  let conversationId = null;
  let chatMode = false;
  let fromChat = false;   // в кнопочный сценарий пришли из свободного диалога
  let fixing = false;     // переспрашиваем одно поле после отказа сервера

  /** Переводит статичные части интерфейса. Уже показанные сообщения не переписываем. */
  function applyLang() {
    panel.setAttribute('lang', lang);
    fab.setAttribute('aria-label', t('fabLabel'));
    $('.close').setAttribute('aria-label', t('closeLabel'));
    backBtn.setAttribute('aria-label', t('back').replace(/^[←\s]+/, ''));
    $('.status-text').textContent = t('status');
    $('#am-sub').textContent = chatMode ? t('subChat') : (cfg?.salon?.tagline || t('sub'));
    input.setAttribute('aria-label', t('answerLabel'));
    form.querySelector('button').setAttribute('aria-label', t('sendLabel'));
    input.placeholder = t(phKey);
    const hours = cfg?.salon?.workHours;
    $('.hours').textContent = hours
      ? t('hours', { days: workDaysLabel(cfg?.salon?.workDays), from: hours.start, to: hours.end })
      : '';
    if (bubble.classList.contains('on')) bubble.textContent = t('tip');
    rerender();
  }

  function setLang(next, { pin = false } = {}) {
    if (pin) langPinned = true;
    if (!next || next === lang) return false;
    lang = next;
    applyLang();
    // Названия услуг и подпись выбранного дня живут на сервере — забираем на новом языке.
    catalogReady = reloadCatalog();
    if (draft.date) relabelDate().then(rerender);
    return true;
  }

  // Язык страницы может меняться переключателем сайта — следим за <html lang>.
  new MutationObserver(() => {
    if (langPinned) return;
    if (!langPinned) setLang(siteLang());
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['lang', 'xml:lang'] });

  let catalogReady = Promise.resolve();

  /** Перезабирает каталог на текущем языке. Кнопки услуг, если они на экране,
      перерисовываются: незачем показывать испанцу русские названия до перезапуска. */
  async function reloadCatalog() {
    if (!cfg) return;
    const want = lang;
    try {
      const fresh = await api(`/api/config?lang=${want}`);
      if (want !== lang) return;          // язык успел смениться снова — ответ уже неактуален
      cfg = fresh;
      // Список услуг на экране — перерисовываем его новыми названиями.
      if (lastChoices?.hint?.k === 'pickService') askService();
    } catch { /* каталог остаётся прежним — язык интерфейса уже переключился */ }
  }

  /** Первое сообщение клиента фиксирует язык диалога. */
  function adoptLang(text) {
    setLang(detectLang(text), { pin: true });
  }

  // Плавная прокрутка к новому сообщению: собственная анимация — надёжнее CSS smooth
  // и сама подстраивается, если контент дорисовался уже во время движения.
  let scrollTimer = 0;
  const scroll = () => {
    clearInterval(scrollTimer);
    const target = () => log.scrollHeight - log.clientHeight;
    if (reduced()) { log.scrollTop = target(); return; }
    const from = log.scrollTop;
    const t0 = Date.now();
    scrollTimer = setInterval(() => {
      const p = Math.min(1, (Date.now() - t0) / 320);
      const e = 1 - Math.pow(1 - p, 3);
      log.scrollTop = from + (target() - from) * e;
      if (p >= 1) { clearInterval(scrollTimer); log.scrollTop = target(); }
    }, 16);
  };

  /**
   * spec — либо готовая строка (текст клиента, ответ модели), либо рецепт
   * { k: ключ словаря, v: переменные или функция, их возвращающая }.
   * Рецепт остаётся на элементе, поэтому при смене языка сообщение перерисовывается.
   */
  const render = (spec) => {
    if (typeof spec === 'string') return spec;
    if (spec.fn) return spec.fn();
    return t(spec.k, typeof spec.v === 'function' ? spec.v() : spec.v);
  };

  // Переписка кнопочного сценария — для панели салона. AI-путь пишет диалог на
  // сервере сам, а шаги «выбрал услугу → выбрал время» жили только в браузере:
  // владелец видел в «Диалогах» пустую карточку «без переписки» у каждой записи.
  const TRANSCRIPT_MAX = 60;
  const TRANSCRIPT_LEN = 500;
  let transcript = [];

  function remember(role, text) {
    const line = String(text || '').trim().slice(0, TRANSCRIPT_LEN);
    if (!line) return;
    transcript.push({ role, text: line });
    if (transcript.length > TRANSCRIPT_MAX) transcript.shift();
  }

  function say(spec, cls = 'bot') {
    const el = document.createElement('div');
    el.className = `msg ${cls}`;
    el.textContent = render(spec);
    if (typeof spec !== 'string') el.__i18n = spec;
    // Ошибки в переписку не пишем: это наш отказ, а не реплика разговора.
    if (cls !== 'err') remember(cls === 'me' ? 'user' : 'assistant', el.textContent);
    log.appendChild(el);
    scroll();
    return el;
  }

  async function botSay(spec, cls = 'bot') {
    const text = render(spec);
    const t0 = document.createElement('div');
    t0.className = 'typing';
    t0.innerHTML = '<i></i><i></i><i></i>';
    log.appendChild(t0);
    scroll();
    await wait(Math.min(750, 260 + text.length * 8));
    t0.remove();
    return say(spec, cls);
  }

  /** Перерисовывает всё, что уже показано: сообщения, карточки и кнопки. */
  function rerender() {
    [...log.children].forEach((el) => {
      if (el.__dateEcho) { el.textContent = draft.dateLabel || el.textContent; return; }
      if (!el.__i18n) return;
      if (el.classList.contains('card-ok')) {
        el.querySelector('b').textContent = t('booked');
        el.querySelector('span').textContent = successText(el.__i18n.summary);
      } else {
        el.textContent = render(el.__i18n);
      }
    });
    if (lastChoices) setChoices(lastChoices.items, lastChoices.hint, { keepSelection: true });
  }

  const TICK = '<svg class="tick" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 8.6 6.2 12.3 13.5 4"/></svg>';

  let lastChoices = null;

  function setChoices(items, hint, opts = {}) {
    lastChoices = items.length ? { items, hint } : null;
    choices.innerHTML = '';
    // Кнопки под набираемый текст меняются на каждой букве — без выезда, иначе мигают.
    choices.classList.toggle('live', Boolean(opts.live));
    if (hint) {
      const h = document.createElement('div');
      h.className = 'hint';
      h.textContent = render(hint);
      choices.appendChild(h);
    }
    items.forEach((it, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.innerHTML = `<span></span>${TICK}`;
      b.querySelector('span').textContent = render(it.label);
      if (it.kind) b.className = it.kind;
      if (!reduced() && !opts.live) b.style.animationDelay = `${(hint ? i + 1 : i) * 55}ms`;
      // «Подтвердить» плавно оживает после того, как сводка дочитана.
      if (it.pending) {
        b.disabled = !opts.keepSelection;
        if (!opts.keepSelection) {
          setTimeout(() => { b.disabled = false; b.classList.remove('pending'); b.classList.add('primary'); }, reduced() ? 0 : 480);
        } else {
          b.classList.remove('pending'); b.classList.add('primary');
        }
      }
      b.addEventListener('click', async () => {
        if (b.disabled) return;
        [...choices.querySelectorAll('button')].forEach((x) => { x.disabled = true; });
        b.classList.add('selected');
        await wait(240);
        choices.innerHTML = '';
        lastChoices = null;
        it.onClick();
      });
      choices.appendChild(b);
    });
    scroll();
  }

  let phKey = 'answerPh';   // ключ текущего плейсхолдера — чтобы пережить смену языка

  /* ---- шаги кнопочного сценария ----------------------------------------
     «Назад» возвращает ровно на один шаг, а не в начало: клиент, ошибившийся
     мастером, не должен заново выбирать услугу и день. Точка возврата — длина
     переписки перед шагом: уходя назад, снимаем сообщения этого шага, и диалог
     не обрастает брошенными ветками, в которых потом не разобраться. */
  const marks = {};

  const stepStart = (name) => { marks[name] = log.children.length; };

  /** Кнопка возврата: имя шага, куда вернуться, и поля черновика, которые он переспросит. */
  const backTo = (name, fn, ...drop) => ({
    label: { k: 'back' }, kind: 'ghost', onClick: () => rewind(name, fn, drop),
  });

  /* «Назад» держим в шапке, а не в конце списка кнопок: среди двух десятков
     дат и времён она терялась, и клиент, выбравший женскую стрижку вместо
     мужской, считал, что выхода нет. В шапке она на одном месте весь диалог. */
  let backSpec = null;

  function setBack(name, fn, ...drop) {
    backSpec = { name, fn, drop };
    backBtn.hidden = false;
  }

  function clearBack() {
    backSpec = null;
    backBtn.hidden = true;
  }

  backBtn.addEventListener('click', () => {
    if (!backSpec) return;
    const { name, fn, drop } = backSpec;
    clearBack();
    rewind(name, fn, drop);
  });

  async function rewind(name, fn, drop) {
    drop.forEach((k) => delete draft[k]);
    choices.innerHTML = '';
    lastChoices = null;
    hideForm();
    // Сначала сворачиваем сообщения шага, и только потом убираем их из разметки:
    // мгновенное исчезновение читается как сбой, а не как «вернулись назад».
    const from = marks[name] ?? 0;
    const doomed = [...log.children].slice(from);
    if (doomed.length && !reduced()) {
      doomed.forEach((el) => el.classList.add('out'));
      await wait(200);
    }
    doomed.forEach((el) => el.remove());
    await fn();
  }

  function askText(key, next) {
    choices.innerHTML = '';
    lastChoices = null;
    form.classList.add('on');
    phKey = key;
    input.placeholder = t(key);
    input.value = '';
    // Телефон набирают с телефона же: без этой подсказки на мобильном
    // открывается буквенная клавиатура, и до цифр нужно жать «123».
    // `type` остаётся текстовым: `tel` в некоторых браузерах подставляет
    // чужой номер из автозаполнения поверх набранного.
    const phone = key === 'phonePh';
    input.inputMode = phone ? 'tel' : 'text';
    input.autocomplete = phone ? 'tel' : 'off';
    focusInput();
    step = next;
  }

  const hideForm = () => { form.classList.remove('on'); step = 'idle'; clearLive(); };

  /* Поле ввода открыто и в кнопочном сценарии: клиенту не обязательно
     проходить пять экранов, если он и так знает, чего хочет. Фразу
     «мужская стрижка к Sam в субботу в 15:00» виджет разбирает сам —
     без AI, — и спрашивает только то, чего в ней не было. */
  function openWish(key = 'wishPh') {
    if (chatMode) return;
    form.classList.add('on');
    // Подсказка в поле — про текущий шаг: на выборе времени полезнее
    // «напишите своё время», чем пример целой фразы с услугой.
    phKey = key;
    input.placeholder = t(key);
    input.value = '';
    input.inputMode = 'text';
    input.autocomplete = 'off';
    input.disabled = false;
    form.querySelector('button').disabled = false;
    step = 'wish';
  }

  applyLang();

  // Код отказа → ключ словаря. Сервер объясняет отказ по-русски (этот текст
  // читает модель), а клиенту нужен его язык, поэтому текст с сервера остаётся
  // запасным вариантом для кода, которого мы ещё не знаем.
  const ERROR_KEYS = {
    slot_taken: 'errSlotTaken', group_full: 'errGroupFull', group_over: 'errGroupOver',
    promo_unknown: 'errPromoUnknown', promo_first: 'errPromoFirst',
    bad_phone: 'errBadPhone', need_country_code: 'errNeedCountryCode', need_name: 'errNeedName',
    blocked: 'errBlocked', daily_limit: 'errDailyLimit', calendar_down: 'errCalendarDown',
  };

  const api = async (path, opts) => {
    const res = await fetch(API + withTenant(path), opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const code = data.detail?.code || data.code;
      const key = ERROR_KEYS[code];
      const err = new Error(key ? t(key)
        : (data.error || data.detail?.error || data.detail || t('apiDown')));
      // Код отказа нужен не только для текста: по нему видно, какое поле
      // переспросить, — иначе клиенту остаётся только начать сначала.
      err.code = code;
      throw err;
    }
    return data;
  };

  // ---- сценарий ----------------------------------------------------------

  async function start() {
    log.innerHTML = '';
    choices.innerHTML = '';
    hideForm();
    Object.keys(draft).forEach((k) => delete draft[k]);
    Object.keys(marks).forEach((k) => delete marks[k]);
    conversationId = null;
    transcript = [];
    clearBack();
    wishRest = null;
    fixing = false;
    // Диалог начат заново — возвращаться в прежний чат больше некуда.
    fromChat = false;
    try {
      if (!cfg) cfg = await api(`/api/config?lang=${lang}`);
    } catch (e) {
      return say({ k: 'offline' }, 'err');
    }
    // Название, инициал и подпись — из настроек бизнеса: один виджет обслуживает разные салоны.
    $('#am-title').textContent = cfg.salon.name || t('status');
    $('.avatar').textContent = (cfg.salon.name || 'A').trim().charAt(0).toUpperCase();
    applyLang();
    const wa = $('.wa');
    if (cfg.salon.whatsapp) wa.href = cfg.salon.whatsapp;
    else wa.style.display = 'none';

    if (cfg.aiEnabled) return startChat();

    // Без AI фразу разбирает сам виджет — приглашение написать честное:
    // «мужская стрижка к Sam в субботу в 15:00» действительно сработает.
    await botSay({ k: 'greetingFree', v: () => ({ salon: cfg.salon.name }) });
    beginBooking();
  }

  // ---- свободный диалог (AI включён) -------------------------------------

  async function startChat() {
    chatMode = true;
    clearBack();
    $('.sub').textContent = t('subChat');
    await botSay({ k: 'greetingChat', v: () => ({ salon: cfg.salon.name }) });
    setChoices(
      [
        ...cfg.services.slice(0, 3).map((s) => ({
          label: s.title,
          onClick: () => sendChat(t('wantService', { title: s.title })),
        })),
        { label: { k: 'fromList' }, kind: 'ghost', onClick: startGuided },
      ],
      { k: 'chatHint' },
    );
    openInput();
  }

  /** Поле ввода в свободном диалоге доступно всегда, кроме момента ожидания ответа. */
  function openInput() {
    form.classList.add('on');
    phKey = 'msgPh';
    input.placeholder = t('msgPh');
    input.value = '';
    input.disabled = false;
    form.querySelector('button').disabled = false;
    step = 'chat';
    focusInput();
  }

  const lockInput = (on) => {
    input.disabled = on;
    form.querySelector('button').disabled = on;
    form.classList.toggle('busy', on);
  };

  /** Запасной путь: кнопочный сценарий, если клиенту так удобнее или чат недоступен. */
  async function startGuided() {
    choices.innerHTML = '';
    hideForm();
    chatMode = false;
    fromChat = true;
    stepStart('guided');
    $('.sub').textContent = cfg?.salon?.tagline || t('sub');
    await botSay({ k: 'guidedStart' });
    beginBooking();
  }

  /** Начало кнопочного сценария. Филиал спрашиваем одинаково и из чата, и без него:
      пока этот шаг жил только в одном пути, салон с включённым AI спрашивал филиал,
      а с выключенным — нет, и клиент из одного района записывался в другой. */
  function beginBooking() {
    if ((cfg.locations || []).length > 1) askLocation();
    else { draft.location = (cfg.locations || [])[0] || null; askService(); }
  }

  async function askLocation() {
    stepStart('location');
    clearBack();
    await botSay({ k: 'whichLocation' });
    setChoices((cfg.locations || []).map((location) => ({
      label: `${location.name}${location.address ? ` — ${location.address}` : ''}`,
      onClick: () => { draft.location = location; say(location.name, 'me'); askService(); },
    })), { k: 'pickLocation' });
  }

  /** Возврат из кнопочного сценария в свободный диалог: переписка продолжается
      с того же места, разговор с ботом не начинается заново. */
  function resumeChat() {
    chatMode = true;
    clearBack();
    $('.sub').textContent = t('subChat');
    setChoices(
      [
        ...cfg.services.slice(0, 3).map((s) => ({
          label: s.title,
          onClick: () => sendChat(t('wantService', { title: s.title })),
        })),
        { label: { k: 'fromList' }, kind: 'ghost', onClick: startGuided },
      ],
      { k: 'chatHint' },
    );
    openInput();
  }

  async function sendChat(text) {
    if (step !== 'chat') return;
    choices.innerHTML = '';
    say(text, 'me');
    lockInput(true);
    const typing = document.createElement('div');
    typing.className = 'typing';
    typing.innerHTML = '<i></i><i></i><i></i>';
    log.appendChild(typing);
    scroll();
    try {
      const res = await api('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, conversationId, lang }),
      });
      conversationId = res.conversationId;
      typing.remove();
      if (res.text) say(res.text);
      if (res.booking) successCard({
        service: res.booking.service, master: res.booking.master,
        dateLabel: res.booking.date_label, time: res.booking.time, address: res.booking.address,
        inCalendar: Boolean(res.booking.html_link),
        manageSent: Boolean(cfg?.notifySends),
      });
      // Варианты ответа от бота: клиенту не обязательно печатать — достаточно нажать.
      const chips = (res.suggestions || [])
        .filter((s) => s && s.label && s.text)
        .map((s) => ({ label: s.label, kind: s.kind || '', onClick: () => sendChat(s.text) }));
      // Сбой на стороне бота — предлагаем тот же путь кнопками, по шагам.
      if (res.fallback) chips.push({ label: { k: 'fromList' }, kind: 'ghost', onClick: startGuided });
      if (res.handoff && cfg.salon.whatsapp) {
        chips.push({ label: { k: 'writeWa' }, kind: 'ghost', onClick: () => window.open(cfg.salon.whatsapp, '_blank') });
      }
      if (chips.length) setChoices(chips);
      scroll();
    } catch (e) {
      typing.remove();
      say(e.message, 'err');
      setChoices([
        { label: { k: 'fromList' }, onClick: startGuided },
        { label: { k: 'writeWa' }, kind: 'ghost', onClick: () => window.open(cfg.salon.whatsapp, '_blank') },
      ]);
    }
    lockInput(false);
    focusInput();
  }


  // ---- свободная фраза в кнопочном сценарии ------------------------------
  /* «Мужская стрижка к Sam в субботу в 15:00» — в одной строке есть услуга,
     мастер, день и время. Разбираем её сами: AI у салона может быть выключен,
     а гонять клиента по пяти экранам ради того, что он уже сказал, незачем.
     Разбор нарочно осторожный: понятое подставляем, остальное спрашиваем
     кнопками, а неузнанную фразу не выдумываем — показываем список услуг. */

  const B = '(?:^|[^\\p{L}\\p{N}])';   // граница слова, работающая и для кириллицы

  /** Слово без регистра, акцентов и «ё» — для сравнения названий с текстом. */
  const fold = (str) => String(str || '').toLowerCase().replace(/ё/g, 'е')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

  /** Грубая основа: «стрижку», «стрижка» и «стрижки» дают одно и то же. */
  const stem = (w) => (w.length >= 6 ? w.slice(0, 5) : w);

  const WEEK_WORDS = [
    'воскрес\\p{L}*|domingo|sunday',
    'понедельн\\p{L}*|lunes|monday',
    'вторник|вторн\\p{L}*|martes|tuesday',
    'сред[ауы]|среда|mi[eé]rcoles|wednesday',
    'четверг\\p{L}*|jueves|thursday',
    'пятниц\\p{L}*|viernes|friday',
    'суббот\\p{L}*|s[aá]bado|saturday',
  ];

  // Порядок важен: «мар» проверяется раньше «ма», иначе март становится маем.
  const MONTH_WORDS = [
    'янв|ene|jan', 'фев|feb', 'мар|mar', 'апр|abr|apr', 'ма|may',
    'июн|jun', 'июл|jul', 'авг|ago|aug', 'сен|sep', 'окт|oct', 'ноя|nov', 'дек|dic|dec',
  ];

  const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    + `-${String(d.getDate()).padStart(2, '0')}`;

  const midnight = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };

  const shiftDays = (n) => { const d = midnight(); d.setDate(d.getDate() + n); return d; };

  /** Ближайшая дата с этим днём недели, начиная с сегодня. */
  function nextWeekday(dow) {
    const d = midnight();
    d.setDate(d.getDate() + ((dow - d.getDay() + 7) % 7));
    return d;
  }

  /** Ближайшая дата с этим числом и месяцем: год клиент не пишет никогда. */
  function nextDate(day, month) {
    const now = midnight();
    const d = new Date(now.getFullYear(), month, day);
    if (d < now) d.setFullYear(d.getFullYear() + 1);
    return d.getMonth() === month ? d : null;   // 31 февраля не существует
  }

  /** Дата из фразы. Возвращает саму дату и кусок текста, который её задал:
      вырезав его, дальше ищем время и не принимаем «29.08» за «29:08». */
  function findDate(text) {
    const rel = [
      [/(послезавтра|pasado\s+ma[nñ]ana|day\s+after\s+tomorrow)/iu, 2],
      [/(завтра|ma[nñ]ana|tomorrow)/iu, 1],
      [/(сегодня|hoy|today)/iu, 0],
    ];
    for (const [re, n] of rel) {
      const m = text.match(re);
      if (m) return { date: isoDate(shiftDays(n)), cut: m[0] };
    }
    for (let i = 0; i < WEEK_WORDS.length; i += 1) {
      const m = text.match(new RegExp(`${B}(${WEEK_WORDS[i]})`, 'iu'));
      if (m) return { date: isoDate(nextWeekday(i)), cut: m[0] };
    }
    const named = text.match(new RegExp(`(\\d{1,2})\\s*(?:de\\s+)?(${MONTH_WORDS.join('|')})\\p{L}*`, 'iu'));
    if (named) {
      const month = MONTH_WORDS.findIndex((w) => new RegExp(`^(?:${w})`, 'iu').test(named[2]));
      const d = month >= 0 ? nextDate(Number(named[1]), month) : null;
      if (d) return { date: isoDate(d), cut: named[0] };
    }
    const numeric = text.match(/(?:^|\s)(\d{1,2})[./-](\d{1,2})(?![\d:])/);
    if (numeric) {
      const d = nextDate(Number(numeric[1]), Number(numeric[2]) - 1);
      if (d) return { date: isoDate(d), cut: numeric[0] };
    }
    return null;
  }

  /** Время из фразы: «15:00», «15.30», «в 15», «a las 15», «at 15». */
  function findTime(text) {
    const exact = text.match(/(?:^|\s)([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)(?!\d)/);
    if (exact) return `${String(exact[1]).padStart(2, '0')}:${exact[2]}`;
    const loose = text.match(
      new RegExp(`(?:${B}(?:в|к|at|a\\s+las|a\\s+la|para\\s+las|hacia\\s+las)\\s*)([01]?\\d|2[0-3])(?![\\d.,:])`, 'iu'),
    );
    if (loose) return `${String(loose[1]).padStart(2, '0')}:00`;
    const hourly = text.match(new RegExp(`${B}([01]?\\d|2[0-3])\\s*(?:час\\p{L}*|ч|h|hs|hrs)${B}`, 'iu'));
    if (hourly) return `${String(hourly[1]).padStart(2, '0')}:00`;
    return null;
  }

  // Служебные слова названий («Corte — con Alex») не решают, какая услуга:
  // иначе «corte de dama con Sam» уезжало в услугу Alex из-за одного «con».
  const STOP = new Set(['con', 'with', 'для', 'los', 'las', 'del', 'the', 'and', 'por', 'para']);
  const meaningful = (str) => fold(str).split(' ').filter((w) => w.length > 2 && !STOP.has(w));

  /** Услуги, названия которых перекликаются с фразой. Одна — берём её,
      несколько — покажем именно их: «стрижка» бывает мужская и женская.
      Недописанное слово тоже считается: пока клиент печатает «женс»,
      над полем уже видны женские стрижки. */
  function findServices(text) {
    const words = meaningful(text);
    const scored = cfg.services.map((service) => {
      const hit = meaningful(service.title).filter((tok) => words.some((w) => stem(w) === stem(tok)
        || (w.length >= 4 && tok.startsWith(w)))).length;
      return { service, hit };
    }).filter((x) => x.hit > 0);
    if (!scored.length) return [];
    const best = Math.max(...scored.map((x) => x.hit));
    return scored.filter((x) => x.hit === best).map((x) => x.service);
  }

  // Имена мастеров в панели латиницей, а клиент пишет «к Alex» и «у Sam».
  const LAT = {
    а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ж: 'zh', з: 'z', и: 'i', й: 'i', к: 'k',
    л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h',
    ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
  };
  const latin = (str) => fold(str).replace(/[а-я]/g, (ch) => LAT[ch] ?? ch);

  function findMaster(text) {
    const words = latin(text).split(' ').filter(Boolean);
    return cfg.masters.find((m) => {
      const name = latin(m.name).split(' ')[0] || '';
      if (name.length <= 2) return false;
      // Имя в падеже («Alex», «Alex») — до двух букв окончания;
      // недописанное («Арте») — от четырёх букв.
      return words.some((w) => (w.startsWith(name) && w.length - name.length <= 2)
        || (w.length >= 4 && name.startsWith(w)));
    }) || null;
  }

  /** Мастера, которые делают эту услугу в выбранном филиале. */
  function mastersFor(service) {
    // Мастер, у которого филиал не указан или указан несуществующий, работает
    // во всех: иначе первый же созданный филиал прячет всех мастеров разом —
    // у них у всех стоит умолчание «main», а у настоящего филиала свой код.
    const known = new Set((cfg.locations || []).map((x) => x.id));
    return cfg.masters.filter((m) => m.services.includes(service.id)
      && (!draft.location || !known.has(m.locationId) || m.locationId === draft.location.id));
  }

  function parseWish(text) {
    const date = findDate(text);
    // Дату вырезаем перед поиском времени: «29.08» — не «29:08», а «3 сентября»
    // не должно превратиться в три часа ночи.
    const rest = date ? text.replace(date.cut, ' ') : text;
    return {
      services: findServices(text),
      master: findMaster(text),
      date: date?.date || null,
      time: findTime(rest),
    };
  }

  /** Названный мастер сужает выбор: «мужская стрижка к Marat» — из двух
      мужских услуг Marat делает одну, спрашивать не о чем. */
  function narrowWish(wish) {
    if (wish.services.length > 1 && wish.master) {
      const his = wish.services.filter((x) => wish.master.services.includes(x.id));
      if (his.length) return { ...wish, services: his };
    }
    return wish;
  }

  /* Остаток фразы, пока клиент уточняет услугу: сказанные мастер, день и время
     не должны пропасть из-за того, что «стрижка» в прайсе не одна. */
  let wishRest = null;

  /** Подставляет всё понятое из фразы и спрашивает только то, чего в ней не было. */
  async function applyWish(text) {
    return applyParsed(parseWish(text));
  }

  async function applyParsed(wish) {
    wishRest = null;
    // Точки возврата всех пропущенных шагов — здесь: «назад» с любого из них
    // снимает подставленное и переспрашивает, а не стирает диалог целиком.
    ['service', 'group', 'master', 'day', 'slot'].forEach(stepStart);

    if (!wish.services.length && !wish.master && !wish.date && !wish.time) {
      await botSay({ k: 'wishUnclear' });
      // Выбранное кнопками не теряем: переспрашиваем текущий шаг, а не весь прайс.
      if (draft.service && draft.master && draft.date) return askSlot();
      if (draft.service && draft.master) return askDay();
      if (draft.service) return askMaster();
      return askService();
    }
    wish = narrowWish(wish);
    if (wish.services.length === 1) [draft.service] = wish.services;
    else if (wish.services.length > 1) {
      wishRest = wish;
      return askService(wish.services);
    }
    if (!draft.service) { wishRest = wish; return askService(); }

    // Число мест в групповой услуге словами не берём — только кнопкой.
    if (Number(draft.service.groupCapacity || 1) > 1 && !(draft.groupSize > 1)) return askGroup();
    draft.groupSize = draft.groupSize || 1;

    const fits = mastersFor(draft.service);
    if (wish.master && fits.includes(wish.master)) draft.master = wish.master;
    else if (wish.master) { await botSay({ k: 'wishNoMaster' }); delete draft.master; }
    if (draft.master && !fits.includes(draft.master)) delete draft.master;
    if (!draft.master) return askMaster();

    // «В 16» на шаге выбора времени: день уже выбран кнопкой — не переспрашиваем.
    const wishDate = wish.date || draft.date;
    if (!wishDate) return askDay();
    let days;
    try { ({ days } = await api(`/api/days?masterId=${draft.master.id}&lang=${lang}`)); }
    catch (e) { return say(e.message, 'err'); }
    const day = days.find((d) => d.date === wishDate);
    if (!day) { await botSay({ k: 'wishNoDay' }); return askDay(); }
    draft.date = day.date; draft.dateLabel = day.label; draft.dateLang = lang;

    if (!wish.time) return askSlot();
    // Проверяем само время, а не сетку кнопок: после записи в 15:00 на 45 минут
    // меню предлагает 17:00, но в 16:00 мастер свободен — туда и записываем.
    let check;
    try { check = await api(slotCheckPath(wish.time)); }
    catch (e) { return say(e.message, 'err'); }
    if (!check.free) return offerNearest(wish.time, check.nearest || []);
    draft.time = wish.time;
    // Что именно бот понял — вслух: клиент должен увидеть свою запись словами,
    // прежде чем оставит имя и телефон.
    await botSay({ fn: () => `${draft.service.title} · ${draft.master.name}\n`
      + `${draft.dateLabel}, ${draft.time}` });
    return askName();
  }

  function askService(only) {
    stepStart('service');
    // Первый шаг: возвращаться некуда, кроме свободного диалога, — и только
    // если клиент пришёл оттуда сам.
    if ((cfg.locations || []).length > 1) setBack('location', askLocation, 'service');
    else if (fromChat) setBack('guided', resumeChat, 'service');
    else clearBack();
    // `only` — короткий список: клиент написал «стрижка», а их две, мужская и
    // женская. Показываем эти две, а не весь прайс заново.
    const list = only && only.length ? only : cfg.services;
    setChoices(
      [
        ...list.map((s) => ({
          // Цену показываем сразу в списке: раньше она появлялась только после
          // выбора услуги, и клиент узнавал стоимость, уже сделав шаг.
          label: s.price
            ? { k: 'serviceItemPriced', v: { title: s.title, n: s.duration, price: s.price } }
            : { k: 'serviceItem', v: { title: s.title, n: s.duration } },
          onClick: () => {
            draft.service = s; say(s.title, 'me');
            // Клиент уточнил услугу — остальное из его фразы уже известно.
            if (wishRest) {
              const rest = wishRest;
              wishRest = null;
              return applyParsed({ ...rest, services: [s] });
            }
            if (Number(s.groupCapacity || 1) > 1) askGroup();
            else { draft.groupSize = 1; askMaster(); }
            return undefined;
          },
        })),
      ],
      { k: only && only.length ? 'wishNarrow' : 'pickService' },
    );
    openWish();
  }

  function askGroup() {
    stepStart('group');
    const capacity = Math.min(100, Number(draft.service.groupCapacity || 1));
    setChoices([
      ...Array.from({ length: capacity }, (_, i) => i + 1).map((n) => ({
        label: { k: 'groupPlaces', v: { n } },
        onClick: () => { draft.groupSize = n; say(t('groupPlaces', { n }), 'me'); askMaster(); },
      })),
    ], { k: 'pickGroup' });
    setBack('service', askService, 'service', 'groupSize');
    openWish();
  }

  async function askMaster() {
    stepStart('master');
    const list = mastersFor(draft.service);
    if (!list.length) {
      await botSay({ k: 'noMasters' }, 'err');
      return;
    }
    await botSay({
      k: 'whichMaster',
      v: () => ({
        title: draft.service.title,
        price: draft.service.price || t('minutes', { n: draft.service.duration }),
      }),
    });
    setChoices(
      [
        ...list.map((m) => ({
          label: m.name,
          onClick: () => { draft.master = m; say(m.name, 'me'); askDay(); },
        })),
      ],
      { k: 'pickMaster' },
    );
    const grouped = Number(draft.service.groupCapacity || 1) > 1;
    setBack(grouped ? 'group' : 'service', grouped ? askGroup : askService,
      'master', 'date', 'dateLabel', 'time');
    openWish('wishPhMaster');
  }

  async function askDay() {
    stepStart('day');
    let days;
    try {
      ({ days } = await api(`/api/days?masterId=${draft.master.id}&lang=${lang}`));
    } catch (e) { return say(e.message, 'err'); }
    if (!days.length) return botSay({ k: 'noDays' }, 'err');

    await botSay({ k: 'whichDay' });
    setChoices(
      [
        ...days.map((d) => ({
          label: d.label,
          onClick: () => {
            draft.date = d.date; draft.dateLabel = d.label; draft.dateLang = lang;
            const echo = say(d.label, 'me');
            echo.__dateEcho = true;   // подпись дня зависит от языка — обновляем вместе с ним
            askSlot();
          },
        })),
      ],
      { k: 'nearestDates' },
    );
    setBack('master', askMaster, 'master', 'date', 'dateLabel', 'time');
    openWish('wishPhDay');
  }

  async function askSlot() {
    stepStart('slot');
    let slots;
    try {
      ({ slots } = await api(
        `/api/slots?masterId=${draft.master.id}&serviceId=${draft.service.id}&date=${draft.date}`,
      ));
    } catch (e) { return say(e.message, 'err'); }

    if (!slots.length) {
      await botSay({ k: 'noSlots' });
      setBack('day', askDay, 'date', 'dateLabel', 'time');
      openWish('wishPhDay');
      return setChoices([
        { ...backTo('day', askDay, 'date', 'dateLabel', 'time'), label: { k: 'otherDate' } },
      ]);
    }
    await botSay({ k: 'freeAt', v: () => ({ master: draft.master.name }) });
    setChoices(
      [
        ...slots.map((s) => ({
          label: s.time,
          kind: 'slot',
          onClick: () => { draft.time = s.time; say(s.time, 'me'); askName(); },
        })),
      ],
      { k: 'slotHint', v: () => ({ date: draft.dateLabel, n: draft.service.duration }) },
    );
    setBack('day', askDay, 'date', 'dateLabel', 'time');
    // Кнопки — это сетка салона, а не все свободные минуты: написанное
    // своими словами «в 16» проверим отдельно и примем, если мастер свободен.
    openWish('wishPhTime');
  }

  const slotCheckPath = (time) => `/api/slot-check?masterId=${encodeURIComponent(draft.master.id)}`
    + `&serviceId=${encodeURIComponent(draft.service.id)}&date=${draft.date}&time=${time}`;

  /** Названное время занято: два-три ближайших свободных окна и «всё время».
      `fix` — время отобрали уже на сводке: остальное клиент ответил, после
      выбора возвращаемся к сводке, а не к имени. */
  async function offerNearest(time, nearest, { fix = false } = {}) {
    stepStart('slot');
    if (!nearest.length) {
      await botSay({ k: 'wishTakenNone', v: () => ({ time, date: draft.dateLabel }) });
      setBack('day', askDay, 'date', 'dateLabel', 'time');
      openWish('wishPhDay');
      return setChoices([
        { ...backTo('day', askDay, 'date', 'dateLabel', 'time'), label: { k: 'otherDate' } },
      ]);
    }
    if (!fix) await botSay({ k: 'wishTaken', v: () => ({ time, date: draft.dateLabel }) });
    setChoices(
      [
        ...nearest.map((s) => ({
          label: s.time,
          kind: 'slot',
          onClick: () => { draft.time = s.time; say(s.time, 'me'); return fix ? confirm() : askName(); },
        })),
        { label: { k: 'allTimes' }, kind: 'ghost', onClick: askSlot },
      ],
      fix ? { k: 'liveNearest' }
        : { k: 'slotHint', v: () => ({ date: draft.dateLabel, n: draft.service.duration }) },
    );
    setBack('day', askDay, 'date', 'dateLabel', 'time');
    if (!fix) openWish('wishPhTime');
    return undefined;
  }

  async function askName() {
    stepStart('name');
    await botSay({ k: 'askName' });
    askText('namePh', 'name');
    setBack('slot', askSlot, 'time', 'name');
    focusInput();
  }

  // Коды соседних стран под рукой: клиент из Аргентины или Бразилии иначе
  // наберёт домашний формат без «+», и номер молча станет уругвайским.
  const PHONE_CODES = ['+598', '+54', '+55', '+1'];

  /**
   * Что не так с номером: '' — всё в порядке, иначе ключ сообщения.
   *
   * Длины местного номера приходят с сервера: пока виджет знал их сам, правила
   * разошлись. Виджет пропускал семизначный номер и номер без «+» у салона
   * из другой страны, сервер отвечал отказом уже после сводки — а починить
   * телефон на том экране было негде.
   */
  function phoneProblem(value) {
    const digits = value.replace(/\D/g, '');
    if (digits.length < 7 || new Set(digits).size < 2) return 'badPhone';
    if (value.startsWith('+')) return '';
    const lengths = cfg?.salon?.phoneLengths || [];
    if (!lengths.length) return '';
    const code = String(cfg?.salon?.phoneCountry || '').replace(/\D/g, '');
    // Номер, уже начинающийся с кода страны, ничего не потерял.
    if (code && digits.startsWith(code) && lengths.includes(digits.length - code.length)) return '';
    if (lengths.includes(digits.length)) return '';
    // Цифр меньше, чем в местном номере, — код страны тут не поможет: номер
    // просто неполный, и совет про код отправляет искать несуществующую ошибку.
    return digits.length < Math.min(...lengths) ? 'badPhone' : 'needCode';
  }

  async function askPhone() {
    stepStart('phone');
    await botSay({ k: 'askPhone' });
    askText('phonePh', 'phone');
    const codes = PHONE_CODES.map((code) => ({
      label: code, kind: 'ghost',
      onClick: () => { input.value = code + ' '; focusInput(); },
    }));
    setChoices(codes, { k: 'phoneCountryHint' });
    setBack('name', askName, 'name', 'phone');
    focusInput();
  }

  // Ответ кнопкой — такая же реплика клиента, как набранный текст. Пока
  // «Пропустить» и «Без промокода» ничего не оставляли в переписке, три вопроса
  // бота шли подряд, будто клиент молчал, и было не понять, на что уже ответил.
  async function askComment() {
    stepStart('comment');
    await botSay({ k: 'askComment' });
    askText('commentPh', 'comment');
    setChoices([
      { label: { k: 'skip' }, kind: 'ghost',
        onClick: () => { draft.comment = ''; say(t('skip'), 'me'); hideForm(); askPromo(); } },
    ]);
    setBack('phone', askPhone, 'phone', 'comment');
    focusInput();
  }

  async function askPromo() {
    stepStart('promo');
    await botSay({ k: 'askPromo' });
    askText('promoPh', 'promoCode');
    setChoices([
      { label: { k: 'noPromo' }, kind: 'ghost',
        onClick: () => { draft.promoCode = ''; say(t('noPromo'), 'me'); hideForm(); askConsent(); } },
    ]);
    setBack('comment', askComment, 'comment', 'promoCode');
    focusInput();
  }

  /* ---- живая строка ---------------------------------------------------
     Пока клиент печатает, виджет показывает, что уже понял. Над полем —
     кнопки ровно под набранное: обе женские стрижки на «женск», мастера этой
     услуги, «записаться на 16:00», если время свободно, или соседние окна,
     если занято. Под кнопками — строка: что понято и чего ещё не хватает.
     Enter или кнопка — и дальше спрашиваем только недостающее. */
  let liveSaved = null;   // кнопки шага до начала набора — вернём, если поле опустеет
  let liveTimer = 0;
  let liveSeq = 0;

  function clearLive() {
    clearTimeout(liveTimer);
    liveSeq += 1;
    wishbar.hidden = true;
    wishbar.innerHTML = '';
    liveSaved = null;
  }

  const shortDate = (iso) => {
    if (draft.date === iso && draft.dateLabel) return draft.dateLabel;
    const [y, m, d] = iso.split('-').map(Number);
    try {
      return new Date(y, m - 1, d).toLocaleDateString(lang === 'en' ? 'en-GB' : lang,
        { weekday: 'short', day: 'numeric', month: 'short' });
    } catch { return iso; }
  };

  /** Известное на сейчас: выбранное кнопками плюс понятое из набранного. */
  function liveState(text) {
    const wish = narrowWish(parseWish(text));
    const service = wish.services.length === 1 ? wish.services[0]
      : (wish.services.length ? null : draft.service || null);
    const master = wish.master || draft.master || null;
    const masterFits = !master || !service || mastersFor(service).includes(master);
    return { wish, service, master, masterFits, date: wish.date || draft.date || null, time: wish.time };
  }

  function renderWishbar(st, check) {
    wishbar.innerHTML = '';
    const need = [];
    const pill = (text, cls) => {
      const el = document.createElement('span');
      el.className = `pill ${cls}`;
      el.textContent = text;
      wishbar.appendChild(el);
    };
    if (st.service) pill(st.service.title, 'ok'); else need.push(t('infoService'));
    if (st.master) pill(st.master.name, st.masterFits ? 'ok' : 'warn'); else need.push(t('infoMaster'));
    if (st.date) pill(shortDate(st.date), 'ok'); else need.push(t('infoDay'));
    if (!st.time) need.push(t('infoTime'));
    else if (!check) pill(st.time, 'ok');
    else pill(t(check.free ? 'liveFree' : 'liveBusy', { time: st.time }), check.free ? 'free' : 'warn');
    if (need.length) {
      const rest = document.createElement('span');
      rest.className = 'need';
      rest.textContent = t('liveNeed', { list: need.join(', ') });
      wishbar.appendChild(rest);
    }
    wishbar.hidden = false;
  }

  function renderLiveChoices(st, check) {
    const { wish } = st;
    const items = [];
    let hint = { k: 'liveHint' };
    if (check?.free) {
      items.push({ label: { k: 'liveBook', v: { date: shortDate(st.date), time: st.time } },
        kind: 'primary', onClick: () => useLive({}) });
    } else if (check) {
      hint = { k: 'liveNearest' };
      (check.nearest || []).forEach((s) => items.push({
        label: s.time, kind: 'slot', onClick: () => useLive({ time: s.time }),
      }));
    } else if (wish.services.length > 1 || (wish.services.length === 1 && wish.services[0] !== draft.service)) {
      wish.services.slice(0, 6).forEach((s) => items.push({
        label: s.price
          ? { k: 'serviceItemPriced', v: { title: s.title, n: s.duration, price: s.price } }
          : { k: 'serviceItem', v: { title: s.title, n: s.duration } },
        onClick: () => useLive({ services: [s] }),
      }));
    } else if (st.service && (!st.master || !st.masterFits)) {
      mastersFor(st.service).forEach((m) => items.push({
        label: m.name, onClick: () => useLive({ services: [st.service], master: m }),
      }));
    }
    if (!check || !items.length) {
      items.push({ label: { k: 'liveGo' }, kind: items.length ? 'ghost' : 'primary', onClick: () => useLive({}) });
    }
    setChoices(items, hint, { live: true });
  }

  function onLive() {
    if (step !== 'wish' || chatMode) return;
    const text = input.value.trim();
    clearTimeout(liveTimer);
    liveSeq += 1;
    if (text.length < 2) {
      wishbar.hidden = true;
      if (liveSaved) {
        const saved = liveSaved;
        liveSaved = null;
        setChoices(saved.items, saved.hint, { keepSelection: true, live: true });
      }
      return;
    }
    if (!liveSaved) liveSaved = lastChoices || { items: [], hint: null };
    // Каталог на языке страницы, а клиент пишет на своём: «мужская стрижка»
    // не находится среди «Men's haircut». Язык берём уже при наборе, как и при
    // отправке, и пересчитываем строку, когда названия придут на нём.
    if (text.length >= 3 && setLang(detectLang(text), { pin: true })) {
      const seq = liveSeq;
      catalogReady.then(() => { if (seq === liveSeq) onLive(); });
    }
    const st = liveState(text);
    renderWishbar(st, null);
    renderLiveChoices(st, null);
    if (!(st.service && st.master && st.masterFits && st.date && st.time)) return;
    // Свободно ли названное время — спрашиваем, когда клиент перестал печатать.
    const seq = liveSeq;
    liveTimer = setTimeout(async () => {
      try {
        const check = await api(`/api/slot-check?masterId=${encodeURIComponent(st.master.id)}`
          + `&serviceId=${encodeURIComponent(st.service.id)}&date=${st.date}&time=${st.time}`);
        if (seq !== liveSeq || step !== 'wish') return;
        renderWishbar(st, check);
        renderLiveChoices(st, check);
      } catch { /* подсказка — не запись: без неё клиент просто нажмёт Enter */ }
    }, 350);
  }

  input.addEventListener('input', onLive);

  /** Кнопка живой строки: набранное уходит репликой клиента, выбранное на кнопке уточняет его. */
  async function useLive(extra) {
    const text = input.value.trim();
    const wish = { ...narrowWish(parseWish(text)), ...extra };
    input.value = '';
    if (text) { adoptLang(text); say(text, 'me'); }
    hideForm();
    choices.innerHTML = '';
    lastChoices = null;
    await applyParsed(wish);
  }

  /* Enter внутри Shadow DOM не отправляет форму сам: неявная отправка ищет
     форму в дереве документа и в теневом её не находит — нажатие гаснет, и
     клиент, набравший имя, думает, что виджет завис. Отправляем вручную. */
  input.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    if (form.requestSubmit) form.requestSubmit();
    else form.dispatchEvent(new Event('submit', { cancelable: true }));
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = input.value.trim();
    if (!value) return;
    adoptLang(value);

    // Свободный диалог: сообщение рисует sendChat. Сюда же уходит всё, что клиент
    // написал вне известного шага, — иначе текст просто повис бы в чате без ответа.
    if (step === 'chat' || (cfg?.aiEnabled && step === 'idle')) {
      input.value = '';
      step = 'chat';
      await sendChat(value);
      return;
    }

    say(value, 'me');
    input.value = '';

    // Свободная фраза посреди кнопочного сценария: клиент написал, чего хочет,
    // — подставляем понятое и спрашиваем только остаток.
    if (step === 'wish') {
      hideForm();
      choices.innerHTML = '';
      lastChoices = null;
      await applyWish(value);
      return;
    }

    if (step === 'name') {
      draft.name = value;
      hideForm();
      await (fixing ? backToSummary() : askPhone());
      return;
    }
    if (step === 'phone') {
      const bad = phoneProblem(value);
      if (bad) return botSay({ k: bad }, 'err');
      draft.phone = value;
      hideForm();
      // Телефон переспрашивали из-за отказа сервера — остальное клиент уже
      // ответил, и гнать его по тем же вопросам заново незачем.
      await (fixing ? backToSummary() : askComment());
      return;
    }
    if (step === 'comment') {
      draft.comment = value;
      hideForm();
      askPromo();
      return;
    }
    if (step === 'promo') {
      draft.promoCode = value.toUpperCase();
      hideForm();
      askConsent();
    }
  });

  /** Напоминания уходят только с явного согласия — без него канал не используется. */
  async function askConsent() {
    stepStart('consent');
    await botSay({ k: 'askConsent' });
    setChoices([
      { label: { k: 'yesNotify' },
        onClick: () => { draft.notifyConsent = true; say(t('yesNotify'), 'me'); confirm(); } },
      { label: { k: 'noNotify' }, kind: 'ghost',
        onClick: () => { draft.notifyConsent = false; say(t('noNotify'), 'me'); confirm(); } },
    ]);
    setBack('promo', askPromo, 'promoCode', 'notifyConsent');
  }

  // Поля, которые сервер отвергает по одному, и шаг, где их спрашивают. Отказ
  // приходит на готовой сводке, когда формы на экране уже нет: без этой таблицы
  // клиенту оставались «другое время» и «начать заново» — то есть выхода не
  // было, и запись обрывалась на последнем шаге.
  const FIXABLE = {
    bad_phone: ['phone', askPhone], need_country_code: ['phone', askPhone],
    need_name: ['name', askName],
  };

  /** Поправленное поле принято — возвращаемся к сводке, а не к следующему вопросу. */
  function backToSummary() {
    fixing = false;
    return confirm();
  }

  async function confirm() {
    stepStart('confirm');
    await relabelDate();
    await botSay({ fn: summaryText });
    setChoices([
      { label: { k: 'confirmBtn' }, kind: 'pending', pending: true, onClick: submit },
      { label: { k: 'restart' }, kind: 'ghost', onClick: start },
    ]);
    // Поправить одну строчку сводки — шаг назад. «Начать заново» остаётся
    // рядом, но уже как осознанный выбор, а не единственный выход.
    setBack('consent', askConsent, 'notifyConsent');
  }

  /** Полный текст сводки и карточки успеха — собираются заново при смене языка. */
  function summaryText() {
    return t('summary', {
      service: draft.service.title, duration: t('minutes', { n: draft.service.duration }),
      master: draft.master.name, date: draft.dateLabel, time: draft.time,
      name: draft.name, phone: draft.phone,
    })
      + (draft.comment ? t('summaryComment', { comment: draft.comment }) : '')
      + (draft.promoCode ? t('summaryPromo', { promo: draft.promoCode }) : '')
      + ((draft.groupSize || 1) > 1 ? t('summaryGroup', { n: draft.groupSize }) : '')
      + t('summaryNotify', { value: draft.notifyConsent ? t('notifyOn') : t('notifyOff') });
  }

  // Про календарь пишем только когда событие туда действительно попало: в демо-режиме
  // backend возвращает htmlLink пустым, и обещать запись в календаре мастера нельзя.
  const successText = (s) =>
    `${s.service} · ${s.master}\n${s.dateLabel}, ${s.time}\n${s.address}\n\n`
    + t(s.inCalendar ? 'bookedNote' : 'bookedNoteLocal')
    // Саму ссылку на «мои записи» виджет не показывает и показывать не должен:
    // записаться можно с чужого телефона, а ссылка открывает все визиты этого
    // номера. Право на неё подтверждает доставка в тот самый WhatsApp.
    + (s.manageSent ? `\n\n${t('manageSent')}` : '');

  /** Если язык сменился после выбора даты, берём подпись дня заново — уже на новом языке. */
  async function relabelDate() {
    if (!draft.date || draft.dateLang === lang) return;
    try {
      const { days } = await api(`/api/days?masterId=${draft.master.id}&lang=${lang}`);
      const found = days.find((d) => d.date === draft.date);
      if (found) { draft.dateLabel = found.label; draft.dateLang = lang; }
    } catch { /* подпись не критична — оставляем прежнюю */ }
  }

  /** Успех показываем только после ответа сервера — до этого время остаётся «в процессе». */
  function successCard(s) {
    const el = document.createElement('div');
    el.className = 'card-ok';
    el.innerHTML = `
      <svg viewBox="0 0 52 52" fill="none" stroke="#D97855" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="26" cy="26" r="23"/><path d="M15 27.5 22.5 35 37 18"/>
      </svg>
      <b></b><span></span>`;
    el.__i18n = { summary: s };
    el.querySelector('b').textContent = t('booked');
    el.querySelector('span').textContent = successText(s);
    log.appendChild(el);
    scroll();
  }

  async function submit() {
    const pend = document.createElement('div');
    pend.className = 'pending';
    pend.innerHTML = '<i></i><span></span>';
    pend.querySelector('span').textContent = t('sending');
    pend.__sending = true;
    log.appendChild(pend);
    scroll();
    try {
      const res = await api('/api/book', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          masterId: draft.master.id,
          serviceId: draft.service.id,
          date: draft.date,
          time: draft.time,
          name: draft.name,
          phone: draft.phone,
          comment: draft.comment,
          promoCode: draft.promoCode || '',
          source: SOURCE,
          groupSize: draft.groupSize || 1,
          notifyConsent: Boolean(draft.notifyConsent),
          lang,
          conversationId,
          transcript,
        }),
      });
      pend.remove();
      successCard({
        ...res.summary,
        inCalendar: Boolean(res.htmlLink),
        manageSent: Boolean(draft.notifyConsent && cfg?.notifySends),
      });
      trackBooking(res);
      clearBack();
      hideForm();
      setChoices([{ label: { k: 'bookAgain' }, kind: 'ghost', onClick: start }]);
    } catch (e) {
      pend.remove();
      const fix = FIXABLE[e.code];
      if (fix) {
        // Сообщение говорим уже на нужном шаге: сначала сворачиваем всё, что
        // было после него, иначе отказ исчезнет вместе с этими сообщениями.
        fixing = true;
        await rewind(fix[0], fix[1], [fix[0]]);
        say(e.message, 'err');
        return;
      }
      say(e.message, 'err');
      // Время успели занять — сразу соседние окна того же дня, а не весь список заново.
      if (e.code === 'slot_taken' && draft.time) {
        try {
          const check = await api(slotCheckPath(draft.time));
          if (check.nearest?.length) {
            const time = draft.time;
            delete draft.time;
            return offerNearest(time, check.nearest, { fix: true });
          }
        } catch { /* ниже — обычный выход */ }
      }
      setChoices([
        { label: { k: 'otherTime' }, onClick: askSlot },
        { label: { k: 'restart' }, kind: 'ghost', onClick: start },
      ]);
    }
  }

  /**
   * Конверсия «запись» для аналитики сайта.
   *
   * Своё событие `bookingagent:booking-complete` остаётся — но требовать от
   * салона написать на него слушатель значит не получить конверсий никогда.
   * Поэтому пиксели дёргаем сами, если они на странице есть: Meta ждёт
   * `Schedule`, Google Ads — событие в `gtag`, GTM — запись в `dataLayer`.
   *
   * Персональных данных не отправляем: услуга, мастер, сумма, промокод и
   * источник. Имя и телефон клиента в рекламный кабинет не уезжают.
   */
  function trackBooking(res) {
    const detail = {
      bookingId: res.bookingId || '',
      service: draft.service?.id || '',
      master: draft.master?.id || '',
      promo: draft.promoCode || '',
      source: SOURCE,
      value: Number(draft.service?.priceAmount || 0),
      currency: draft.service?.currency || 'UYU',
    };
    window.dispatchEvent(new CustomEvent('bookingagent:booking-complete', { detail }));
    try {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({ event: 'booking_complete', ...detail });
      // Meta: «Schedule» — стандартное событие записи на приём.
      if (typeof window.fbq === 'function') {
        window.fbq('track', 'Schedule',
          detail.value ? { value: detail.value, currency: detail.currency } : {});
      }
      if (typeof window.gtag === 'function') {
        window.gtag('event', 'booking_complete', {
          value: detail.value, currency: detail.currency,
          items: [{ item_id: detail.service }],
        });
      }
    } catch { /* аналитика не должна ломать запись — она уже создана */ }
  }

  // ---- подсказка у закрытой кнопки ---------------------------------------
  let tipTimer = null, tipSeen = false;

  function showTip() {
    if (tipSeen || panel.classList.contains('open') || reduced()) return;
    bubble.textContent = t('tip');
    bubble.classList.add('on');
    setTimeout(() => bubble.classList.remove('on'), 4000);
  }
  const hideTip = () => { bubble.classList.remove('on'); };

  // Первый показ через 1.5 с после загрузки, дальше не чаще раза в 18 с.
  if (!reduced()) {
    setTimeout(() => { showTip(); tipTimer = setInterval(showTip, 18000); }, 1500);
  }

  // ---- телефон: страница под окном и клавиатура ---------------------------
  // На полном экране окно перекрывает сайт целиком. Если страницу под ним не
  // придержать, палец скроллит её, а не переписку, и после закрытия клиент
  // оказывается в другом месте сайта.
  let pageY = 0, pageLocked = false;
  const pageStyle = {};

  function lockPage() {
    if (pageLocked || !fullscreen.matches) return;
    pageY = window.scrollY || window.pageYOffset || 0;
    const b = document.body;
    ['position', 'top', 'left', 'right', 'width'].forEach((k) => { pageStyle[k] = b.style[k]; });
    b.style.position = 'fixed';
    b.style.top = `-${pageY}px`;
    b.style.left = '0';
    b.style.right = '0';
    b.style.width = '100%';
    pageLocked = true;
  }

  function unlockPage() {
    if (!pageLocked) return;
    const b = document.body;
    Object.keys(pageStyle).forEach((k) => { b.style[k] = pageStyle[k] || ''; });
    pageLocked = false;
    window.scrollTo(0, pageY);
  }

  // Клавиатура не уменьшает окно браузера — она уменьшает видимую область.
  // Без этой подгонки поле ввода прячется под клавиатурой, и телефон начинает
  // возить страницу вверх-вниз в попытке его показать.
  const vv = window.visualViewport;

  function fitViewport() {
    if (!vv) return;
    if (!fullscreen.matches || !panel.classList.contains('open')) {
      host.style.removeProperty('--vv-h');
      host.style.removeProperty('--vv-top');
      return;
    }
    host.style.setProperty('--vv-h', `${Math.round(vv.height)}px`);
    host.style.setProperty('--vv-top', `${Math.round(vv.offsetTop)}px`);
  }

  if (vv) {
    vv.addEventListener('resize', () => { fitViewport(); scroll(); });
    vv.addEventListener('scroll', fitViewport);
  }

  // Поворот экрана или смена размера окна: полноэкранный режим включается и
  // выключается на лету — держим страницу и высоту окна в согласии с ним.
  fullscreen.addEventListener('change', () => {
    if (fullscreen.matches) { if (panel.classList.contains('open')) lockPage(); }
    else unlockPage();
    fitViewport();
  });

  // ---- открытие/закрытие -------------------------------------------------
  let opener = null;   // элемент страницы, с которого открыли окно, — ему вернём фокус

  async function open() {
    // После первого открытия подсказка не возвращается.
    tipSeen = true;
    hideTip();
    if (tipTimer) { clearInterval(tipTimer); tipTimer = null; }
    panel.classList.add('open');
    dock.classList.add('hidden');   // на полноэкранном мобильном кнопка не должна лежать поверх диалога
    fab.setAttribute('aria-expanded', 'true');
    lockPage();
    fitViewport();
    panel.focus({ preventScroll: true });
    if (!log.children.length) {
      await wait(180); // сначала показывается шапка, затем первое сообщение
      start();
    }
  }

  function close() {
    panel.classList.remove('open');
    dock.classList.remove('hidden');
    fitViewport();
    unlockPage();
    fab.setAttribute('aria-expanded', 'false');
    // Фокус возвращается тому, кто открыл окно: кнопке на странице, если она была.
    const back = opener && opener.isConnected ? opener : fab;
    opener = null;
    back.focus({ preventScroll: true });
  }

  fab.addEventListener('click', () => (panel.classList.contains('open') ? close() : open()));
  $('.close').addEventListener('click', close);
  bubble.addEventListener('click', open);
  root.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && panel.classList.contains('open')) { e.stopPropagation(); close(); }
  });

  // ---- запуск с самой страницы -------------------------------------------
  // Любой элемент с `data-demo-salon-open` открывает окно записи. Делегирование на
  // документе, а не обработчик на каждом узле: строгий CSP сайта запрещает inline-onclick,
  // а кнопка может появиться и после загрузки виджета.
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest?.('[data-demo-salon-open]');
    if (!trigger) return;
    e.preventDefault();
    opener = trigger;
    if (!panel.classList.contains('open')) open();
  });

  window.BookingShowcase = {
    open: () => { if (!panel.classList.contains('open')) open(); },
    close,
  };
})();
