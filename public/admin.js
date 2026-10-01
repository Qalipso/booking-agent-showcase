/* Панель управления Demo Salon.
 *
 * Форма настроек целиком генерируется из config/schema.json — добавили поле в
 * схему, оно само появилось здесь, в валидации и в справке по .env.
 *
 * Автосохранение: правки уходят на сервер через 900 мс после последнего ввода.
 * Форма при этом НЕ перерисовывается — иначе слетал бы фокус и каретка.
 *
 * Примитивы интерфейса (иконки, тосты, диалоги, панель) живут в admin/ui.js.
 */

const { el, icon, toast, drawer, actionMenu, emptyState, errorState,
        skeletonTable, skeletonCards } = window.UI;
const confirmDialog = window.UI.confirm;
const promptDialog = window.UI.prompt;

const $ = (s) => document.querySelector(s);

const WEEKDAYS = [
  { value: 1, label: 'Пн' }, { value: 2, label: 'Вт' }, { value: 3, label: 'Ср' },
  { value: 4, label: 'Чт' }, { value: 5, label: 'Пт' }, { value: 6, label: 'Сб' },
  { value: 0, label: 'Вс' },
];
const MASK = '••••••••';
// Винительный падеж для кнопки «Добавить …»: «Добавить мастер» читается как ошибка.
const ACCUSATIVE = { 'Мастер': 'мастера', 'Услуга': 'услугу' };
const addLabel = (itemLabel) => ACCUSATIVE[itemLabel] ?? itemLabel.toLowerCase();
const AUTOSAVE_DELAY = 900;
const PAGE_SIZE = 12;

/* ============================== ДОСТУП ================================== */
/* Вход по почте и паролю. Ключ сессии живёт в HttpOnly-cookie: из JavaScript
   его не прочитать, поэтому кража через XSS ничего не даёт. Здесь не хранится
   ничего — состояние входа знает только сервер. */

/** Единственная точка запроса к админ-API. */
async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, { ...options, credentials: 'same-origin' });
  } catch (cause) {
    // Помечаем именно обрыв связи. Без метки экран не отличит его от собственной
    // ошибки разметки и в обоих случаях будет валить вину на сервер.
    const err = new Error('Сеть недоступна');
    err.network = true;
    err.cause = cause;
    throw err;
  }
  if (res.status === 401) {
    askLogin();
    throw new Error('Нужен вход');
  }
  if (res.status === 503) {
    // 503 отдаёт сервер, у которого отвалилась база. Панель при этом никто не
    // выключал, и говорить «отключена» — значит отправить человека искать рубильник,
    // которого нет.
    askLogin('Сервер временно недоступен: не отвечает база данных. Панель откроется, когда он поднимется.',
      { blocked: true });
    throw new Error('Сервер недоступен');
  }
  return res;
}

const apiJson = (path, options) => api(path, options).then((r) => r.json());

/** То же, но с внятным отказом: код ответа доезжает до экрана.

    `apiJson` на неуспешном ответе просто пытается разобрать тело, и экран
    получает ошибку разбора JSON — неотличимую от оборванной связи. Пока
    перезапускается сервер, это не мелочь: рабочая страница выглядит сломанной
    насовсем, и человек идёт чинить то, что чинить не нужно. */
async function apiData(path, options) {
  const res = await api(path, options);
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/** Причина отказа словами. Разные беды — разные действия.

    Третий случай — сбой самой панели: исключение при отрисовке долетает в тот же
    `catch`, что и сетевая беда. Пока он выдавал себя за молчание сервера, сломанный
    экран выглядел временным: человек жал «Повторить», перезапускал контейнер и не
    чинил то единственное, что сломано. Теперь ошибка называет себя и падает в
    консоль со стеком. */
const loadFailure = (err) => {
  if (err?.status) return `Сервер ответил ошибкой ${err.status}.`;
  if (err?.network) return 'Сервер не ответил — возможно, он перезапускается. Попробуйте ещё раз.';
  console.error('Сбой панели при отрисовке:', err);
  return `Сбой панели: ${err?.message || err}. Перезагрузите страницу; если повторится — это ошибка в панели.`;
};

/** POST на эндпоинты входа. Ошибку возвращает текстом, а не бросает: форме
    нужно показать причину, а не свалиться. */
async function authPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  let payload = {};
  try { payload = await res.json(); } catch { /* пустой ответ — не беда */ }
  return { ok: res.ok, status: res.status, detail: payload.detail || '', data: payload };
}

/** Экран входа. Пока в базе нет ни одного администратора — предлагает его создать. */
async function askLogin(message = '', { blocked = false } = {}) {
  $('#shell').hidden = true;
  if (document.querySelector('#gate')) {
    const hint = document.querySelector('#gate .hint');
    if (hint && message) hint.textContent = message;
    return;
  }

  let state = { needsSetup: false };
  try { state = await (await fetch('/api/admin/auth/state', { credentials: 'same-origin' })).json(); }
  catch { /* сервер недоступен — покажем обычную форму входа */ }
  const setup = Boolean(state.needsSetup);

  const email = el('input', { type: 'email', placeholder: 'you@example.com', id: 'gateEmail' });
  email.setAttribute('autocomplete', 'username');
  const password = el('input', { type: 'password', placeholder: '••••••••', id: 'gatePassword' });
  password.setAttribute('autocomplete', setup ? 'new-password' : 'current-password');
  // Поле кода показываем только когда сервер сказал, что без него не пускает:
  // спрашивать его у всех подряд — лишний шаг для тех, у кого 2FA не включена.
  const code = el('input', { type: 'text', placeholder: '123456', id: 'gateCode', inputMode: 'numeric' });
  code.setAttribute('autocomplete', 'one-time-code');
  const codeField = el('div', { className: 'field' },
    el('label', { htmlFor: 'gateCode' }, 'Код из приложения'), code);
  // Прячем стилем, а не атрибутом hidden: у .field в теме задан display,
  // который перебивает hidden, и поле осталось бы на экране.
  codeField.style.display = 'none';
  const showCodeField = () => { codeField.style.display = ''; };
  const codeVisible = () => codeField.style.display !== 'none';

  const hint = el('p', { className: 'hint' }, message
    || (setup ? 'Панель ещё никому не принадлежит — создайте администратора.'
              : 'Войдите по почте и паролю.'));
  const enter = el('button', {
    className: 'btn btn-primary',
    textContent: setup ? 'Создать администратора' : 'Войти',
  });

  const submit = async () => {
    if (!email.value.trim() || !password.value) { (email.value ? password : email).focus(); return; }
    enter.disabled = true;
    const body = { email: email.value.trim(), password: password.value };
    if (codeVisible() && code.value.trim()) body.code = code.value.trim();
    const r = await authPost(setup ? '/api/admin/auth/register' : '/api/admin/auth/login', body);
    enter.disabled = false;
    if (r.ok) { gate.remove(); boot(); return; }
    if (/код/i.test(r.detail)) {
      // Пароль подошёл — не хватает второго фактора: раскрываем поле и не
      // заставляем набирать пароль заново.
      showCodeField();
      code.focus();
    }
    hint.textContent = r.detail || 'Не удалось войти';
    password.select();
  };

  enter.onclick = submit;
  for (const field of [email, password, code]) {
    field.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  }

  const gate = el('div', { className: 'gate', id: 'gate' },
    el('div', { className: 'gate-box' },
      el('div', { className: 'logo' }, 'A'),
      el('h1', {}, 'Demo Salon'),
      hint,
      blocked ? null : el('div', { className: 'field' },
        el('label', { htmlFor: 'gateEmail' }, 'Почта'), email),
      blocked ? null : el('div', { className: 'field' },
        el('label', { htmlFor: 'gatePassword' }, 'Пароль'), password),
      blocked ? null : codeField,
      blocked ? null : enter));
  document.body.append(gate);
  email.focus();
}

/** Выход: сервер гасит сессию, страница возвращается к форме входа. */
async function logout() {
  await authPost('/api/admin/auth/logout');
  location.reload();
}

/** Небольшое модальное окно поверх панели: свой, чтобы не звать prompt(),
    который не даёт ни пароля со звёздочками, ни внятной ошибки. */
function overlay(title, fields, onSubmit, { submitLabel = 'Сохранить', note = '' } = {}) {
  const hint = el('p', { className: 'hint' }, note);
  const go = el('button', { className: 'btn btn-primary', textContent: submitLabel });
  const cancel = el('button', { className: 'btn', textContent: 'Отмена' });
  const box = el('div', { className: 'gate-box' },
    el('h1', {}, title), hint,
    ...fields.map((f) => el('div', { className: 'field' },
      el('label', { htmlFor: f.input.id }, f.label), f.input)),
    el('div', { className: 'row' }, go, cancel));
  const gate = el('div', { className: 'gate' }, box);

  const close = () => gate.remove();
  cancel.onclick = close;
  go.onclick = async () => {
    go.disabled = true;
    const err = await onSubmit();
    go.disabled = false;
    if (err) { hint.textContent = err; return; }
    close();
  };
  document.body.append(gate);
  fields[0]?.input.focus();
  return { close, setHint: (t) => { hint.textContent = t; } };
}

function askPasswordChange() {
  const current = el('input', { type: 'password', id: 'pwCurrent' });
  const next = el('input', { type: 'password', id: 'pwNext' });
  next.setAttribute('autocomplete', 'new-password');
  overlay('Смена пароля', [
    { label: 'Текущий пароль', input: current },
    { label: 'Новый пароль', input: next },
  ], async () => {
    const r = await authPost('/api/admin/auth/password',
      { currentPassword: current.value, newPassword: next.value });
    if (!r.ok) return r.detail || 'Не удалось сменить пароль';
    toast('ok', 'Пароль изменён', 'Прежние сессии закрыты.');
    return '';
  }, { note: 'Не короче 10 символов, буквы и цифры. Все прежние сессии закроются.' });
}

async function askTotp() {
  const state = await (await fetch('/api/admin/auth/state', { credentials: 'same-origin' })).json();
  if (state.totpEnabled) {
    const password = el('input', { type: 'password', id: 'totpPass' });
    overlay('Выключить двухфакторный вход', [{ label: 'Пароль', input: password }], async () => {
      const r = await authPost('/api/admin/auth/totp/disable', { email: state.email, password: password.value });
      if (!r.ok) return r.detail || 'Не удалось выключить';
      toast('ok', 'Двухфакторный вход выключен', 'Теперь достаточно пароля.');
      return '';
    }, { submitLabel: 'Выключить', note: 'Подтвердите паролем — вкладки без пароля этого сделать не смогут.' });
    return;
  }

  const started = await authPost('/api/admin/auth/totp/start');
  if (!started.ok) { toast('err', 'Не удалось начать настройку', started.detail); return; }
  const secret = started.data.secret;
  const code = el('input', { type: 'text', id: 'totpCode', inputMode: 'numeric', placeholder: '123456' });
  overlay('Двухфакторный вход', [{ label: 'Код из приложения', input: code }], async () => {
    const r = await authPost('/api/admin/auth/totp/enable', { secret, code: code.value });
    if (!r.ok) return r.detail || 'Код не подошёл';
    toast('ok', 'Двухфакторный вход включён', 'При следующем входе спросим код.');
    return '';
  }, {
    submitLabel: 'Включить',
    // Ключ показываем текстом: рисовать QR-код зависимостью ради одного экрана
    // не стоит, а вручную его вводят один раз.
    note: `Добавьте ключ в Google Authenticator или 1Password: ${secret}`,
  });
}

/* ============================== СОСТОЯНИЕ =============================== */

const get = (obj, path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
const set = (obj, path, value) => {
  const keys = path.split('.');
  const last = keys.pop();
  const t = keys.reduce((o, k) => (o[k] ??= {}), obj);
  t[last] = value;
};

let schema = null;
let data = null;
let active = null;
let tenants = [];
/** Кто вошёл: от роли зависит, какие разделы показывать. Права проверяет
    сервер — спрятанный раздел это удобство, а не защита. */
let me = { email: '', name: '', role: '' };
const isOwner = () => me.role !== 'admin';   // без сессии (машинный токен) — полный доступ
let googleCalendars = [];
// Филиалы: нужны форме мастера. Без них привязка к филиалу — это ввод
// случайного идентификатора руками, а промах в нём прячет мастера от клиентов.
let salonLocations = [];
let googleStatus = null;
let tenant = new URLSearchParams(location.search).get('tenant') || '';
let saveTimer = null;
let saving = false;
let dirty = false;
let charts = {};

/** Любой запрос адресуется конкретному бизнесу. */
const url = (path) => path + (path.includes('?') ? '&' : '?') + 'tenant=' + encodeURIComponent(tenant);
const current = () => tenants.find((t) => t.slug === tenant);

/* ============================== СОХРАНЕНИЕ ============================== */

function status(state, text) {
  const box = $('#saveState');
  box.className = `autosave ${state}`;
  box.textContent = text;
}
const status_ = status;

function scheduleSave() {
  dirty = true;
  status('pending', 'Есть несохранённые правки');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, AUTOSAVE_DELAY);
}

async function save({ immediate = false } = {}) {
  clearTimeout(saveTimer);
  if (saving) {
    if (immediate) saveTimer = setTimeout(save, 200);
    return;
  }
  saving = true;
  status('saving', 'Сохраняю…');
  try {
    const payload = { ...data };
    delete payload.__env;
    const res = await api(url('/api/admin/config'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const errors = body?.detail?.errors ?? body?.errors ?? [body?.detail ?? 'Ошибка сохранения'];
      showErrors(errors);
      status('error', `Не сохранено: ${errors.length} ${plural(errors.length)}`);
      toast('err', 'Настройки не сохранены', errors[0]);
      return;
    }
    dirty = false;
    showErrors([]);
    data.__env = body.env;
    updateEnvBox();
    updateRuntimeBadges(body);
    refreshGoogleBlock();   // ввели Client ID — кнопка входа должна ожить сразу
    status('saved', `Сохранено в ${new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`);
  } catch (e) {
    status('error', 'Сервер недоступен');
    if (!String(e.message).includes('вход')) toast('err', 'Сервер недоступен', 'Правки остались в форме — попробуйте сохранить ещё раз.');
  } finally {
    saving = false;
  }
}

const plural = (n) => (n % 10 === 1 && n % 100 !== 11 ? 'ошибка' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'ошибки' : 'ошибок');

/* ============================== ПОЛЯ ФОРМЫ ============================== */

function visible(field, scope) {
  if (!field.showIf) return true;
  return Object.entries(field.showIf).every(([k, v]) => {
    const actual = get(scope, k);
    return typeof v === 'boolean' ? Boolean(actual) === v : actual === v;
  });
}

/* Поля формы построены на Shoelace: подпись, подсказка, состояния и доступность
   уже внутри компонента, а вид задаётся темой admin/shoelace-theme.css.
   Наборы чипов (дни недели, услуги мастера) остаются своими — это не стандартный
   элемент формы, а компактный множественный выбор. */

const slAttrs = (field, value) => ({
  label: field.label,
  helpText: field.hint ?? '',
  placeholder: field.placeholder ?? '',
  value: value ?? '',
  size: 'medium',
  // Автозаполнение браузера здесь только вредит: менеджер паролей подставлял почту
  // администратора в Client ID, а сохранённый пароль — в Client Secret, и настройки
  // уезжали на сервер испорченными.
  autocomplete: 'off',
});

function renderField(field, scope, onStructuralChange) {
  if (field.type === 'hidden') return null;   // служебные значения формой не правятся
  const wide = ['textarea', 'weekdays', 'serviceRefs'].includes(field.type);
  const wrap = el('div', { className: `field${wide ? ' wide' : ''}` });
  const value = get(scope, field.key);
  const id = `f-${Math.random().toString(36).slice(2, 9)}`;

  const changed = () => { scheduleSave(); };
  const commit = (raw) => {
    set(scope, field.key, field.type === 'number' && raw !== '' ? Number(raw) : raw);
    changed();
  };
  let control;

  switch (field.type) {
    case 'textarea':
      control = el('sl-textarea', { ...slAttrs(field, value), id, resize: 'vertical', rows: 4 });
      break;
    case 'select': {
      control = el('sl-select', { ...slAttrs(field, value), id, hoist: true });
      field.options.forEach((o) => {
        const v = typeof o === 'string' ? o : o.value;
        const label = typeof o === 'string' ? o : o.label;
        control.append(el('sl-option', { value: v, textContent: label }));
      });
      // Значение выставляем после опций: до их появления select его отбросит.
      control.value = value ?? '';
      break;
    }
    case 'bool': {
      // Переключатель, а не голая галочка: состояние читается с одного взгляда.
      control = el('sl-switch', { id, checked: Boolean(value), size: 'medium' },
        el('span', {}, field.label),
        field.hint ? el('small', { className: 'switch-hint' }, field.hint) : null);
      control.addEventListener('sl-change', () => {
        set(scope, field.key, control.checked);
        changed();
        onStructuralChange?.();
      });
      wrap.append(control);
      return wrap;
    }
    case 'weekdays': {
      wrap.append(el('label', { className: 'group-label' }, field.label,
        field.required ? el('span', { className: 'req' }, ' *') : null));
      control = el('div', { className: 'chips', attrs: { role: 'group', 'aria-label': field.label } });
      WEEKDAYS.forEach((d) => {
        const on = (value ?? []).map(Number).includes(d.value);
        const cb = el('input', { type: 'checkbox', checked: on, value: String(d.value) });
        const lb = el('label', { className: on ? 'on' : '' }, cb, d.label);
        cb.onchange = () => {
          lb.classList.toggle('on', cb.checked);
          set(scope, field.key,
            [...control.querySelectorAll('input')].filter((i) => i.checked).map((i) => Number(i.value)).sort((a, b) => a - b));
          changed();
        };
        control.append(lb);
      });
      wrap.append(control, quickDays(control, scope, field, changed));
      break;
    }
    case 'serviceRefs': {
      wrap.append(el('label', { className: 'group-label' }, field.label,
        field.required ? el('span', { className: 'req' }, ' *') : null));
      control = el('div', { className: 'chips', attrs: { role: 'group', 'aria-label': field.label } });
      (data.services ?? []).forEach((s) => {
        const on = (value ?? []).includes(s.id);
        const cb = el('input', { type: 'checkbox', checked: on, value: s.id });
        const lb = el('label', { className: on ? 'on' : '' }, cb, s.title || s.id);
        cb.onchange = () => {
          lb.classList.toggle('on', cb.checked);
          set(scope, field.key, [...control.querySelectorAll('input')].filter((i) => i.checked).map((i) => i.value));
          changed();
        };
        control.append(lb);
      });
      // Услуга могла исчезнуть из справочника, а ссылка на неё — остаться.
      // Без своего чипа снять её нечем: форма рисует только живые услуги, а
      // сохранение блокирует «неизвестная услуга «код»» — панель запиралась.
      const alive = new Set((data.services ?? []).map((s) => s.id));
      (value ?? []).filter((sid) => !alive.has(sid)).forEach((sid) => {
        const cb = el('input', { type: 'checkbox', checked: true, value: sid });
        const lb = el('label', { className: 'on missing' }, cb, `${sid} — услуга удалена`);
        cb.onchange = () => {
          lb.classList.toggle('on', cb.checked);
          set(scope, field.key, [...control.querySelectorAll('input')].filter((i) => i.checked).map((i) => i.value));
          changed();
        };
        control.append(lb);
      });
      if (!(data.services ?? []).length) control.append(el('small', {}, 'Сначала добавьте услуги.'));
      wrap.append(control);
      break;
    }
    case 'secret':
      control = el('sl-input', {
        ...slAttrs(field, value), id, type: 'password', passwordToggle: true,
        placeholder: field.placeholder ?? MASK, autocomplete: 'off',
      });
      // Маску стираем при первом фокусе — иначе владелец правил бы точки.
      control.addEventListener('sl-focus', () => { if (control.value === MASK) control.value = ''; });
      break;
    case 'number':
      control = el('sl-input', {
        ...slAttrs(field, value), id, type: 'number', noSpinButtons: false,
        min: field.min ?? null, max: field.max ?? null,
      });
      break;
    case 'time':
      control = el('sl-input', { ...slAttrs(field, value), id, type: 'time' });
      break;
    case 'url':
      control = el('sl-input', { ...slAttrs(field, value), id, type: 'url', inputmode: 'url' });
      break;
    default:
      if (field.key === 'locationId' && salonLocations.length) {
        // Пусто — «во всех филиалах»: так же это понимает виджет, и мастер с
        // умолчанием не исчезает из записи после создания первого филиала.
        control = el('sl-select', { ...slAttrs(field, value), id, hoist: true });
        control.append(el('sl-option', { value: '', textContent: 'Во всех филиалах' }));
        salonLocations.forEach((x) => control.append(el('sl-option', {
          value: x.id, textContent: x.address ? `${x.name} — ${x.address}` : x.name,
        })));
        control.value = salonLocations.some((x) => x.id === value) ? value : '';
      } else if (field.key === 'calendarId' && googleCalendars.length) {
        // Google подключён — мастер выбирает календарь из списка, а не вводит ID.
        control = el('sl-select', { ...slAttrs(field, value), id, hoist: true });
        const known = googleCalendars.some((c) => c.id === value);
        if (!known && value) control.append(el('sl-option', { value, textContent: value }));
        googleCalendars.forEach((c) => control.append(el('sl-option', {
          value: c.id,
          textContent: c.primary ? `${c.title} (основной)` : c.title,
        })));
        control.value = value ?? '';
      } else {
        control = el('sl-input', { ...slAttrs(field, value), id, type: 'text' });
      }
  }

  if (!['weekdays', 'serviceRefs'].includes(field.type)) {
    if (field.required) control.setAttribute('data-required', '');
    wrap.append(control);
    // sl-input — при вводе, sl-change — при фиксации значения. Оба сохраняем:
    // автосохранение не должно ждать, пока поле потеряет фокус.
    control.addEventListener('sl-input', () => commit(control.value));
    control.addEventListener('sl-change', () => {
      commit(control.value);
      // select и showIf-поля меняют состав формы — тут перерисовка нужна.
      if (field.type === 'select') onStructuralChange?.();
    });
  }

  // Подсказку у полей Shoelace рисует сам компонент (help-text); своим блоком
  // она нужна только наборам чипов.
  if (field.hint && ['weekdays', 'serviceRefs'].includes(field.type)) {
    wrap.append(el('small', {}, field.hint));
  }
  return wrap;
}

/** Быстрые пресеты графика — руками кликать семь дней утомительно. */
function quickDays(control, scope, field, changed) {
  const apply = (days) => {
    set(scope, field.key, days);
    control.querySelectorAll('label').forEach((lb) => {
      const cb = lb.querySelector('input');
      cb.checked = days.includes(Number(cb.value));
      lb.classList.toggle('on', cb.checked);
    });
    changed();
  };
  const row = el('div', { className: 'quick' });
  [['Пн–Вс', [0, 1, 2, 3, 4, 5, 6]], ['Пн–Сб', [1, 2, 3, 4, 5, 6]], ['Пн–Пт', [1, 2, 3, 4, 5]]]
    .forEach(([label, days]) => {
      const b = el('button', { type: 'button', textContent: label });
      b.onclick = () => apply(days);
      row.append(b);
    });
  return row;
}

/* ============================== СЕКЦИИ СХЕМЫ ============================ */

function renderObjectSection(section) {
  const scope = (data[section.id] ??= {});
  const grid = el('div', { className: 'grid' });
  const redraw = () => grid.replaceChildren(...build());
  const build = () => section.fields.filter((f) => visible(f, scope))
    .map((f) => renderField(f, scope, redraw)).filter(Boolean);
  grid.append(...build());
  return grid;
}

/** Поля секции схемы по её id — когда на одном экране их несколько. */
function sectionFields(id) {
  const section = schema.sections.find((s) => s.id === id);
  return section ? renderObjectSection(section) : null;
}

/** Блок экрана: заголовок, пояснение и содержимое. */
function subSection(title, lede, ...content) {
  return el('div', { className: 'sub' },
    el('h3', { className: 'section-title' }, title),
    lede ? el('p', { className: 'hint' }, lede) : null,
    ...content.filter(Boolean));
}

function renderListSection(section) {
  const box = el('div', { dataset: { section: section.id } });
  const items = (data[section.id] ??= []);

  const draw = () => {
    box.replaceChildren();
    items.forEach((item, idx) => {
      const card = el('div', { className: 'item' });
      const name = () => item.title || item.name || '';
      const title = el('strong', {}, `${section.itemLabel} ${idx + 1}${name() ? ` — ${name()}` : ''}`);

      const del = el('button', {
        className: 'btn btn-icon', type: 'button',
        attrs: { 'aria-label': `Удалить: ${name() || section.itemLabel}` },
      }, icon('trash', { size: 16 }));
      del.onclick = async () => {
        const ok = await confirmDialog({
          title: `Удалить «${name() || section.itemLabel.toLowerCase()}»?`,
          message: 'Настройка исчезнет из виджета сразу после сохранения. Уже созданные записи останутся.',
          confirmLabel: 'Удалить', danger: true,
        });
        if (!ok) return;
        const goneId = section.id === 'services' ? item.id : null;
        items.splice(idx, 1);
        // Удалённая услуга не должна остаться в списках мастеров: сохранение
        // отклонялось бы по «неизвестная услуга», а снять её было бы негде.
        if (goneId) mapServiceRefs((list) => list.filter((sid) => sid !== goneId));
        draw();
        if (section.id === 'services') redrawMasters();
        scheduleSave();
      };
      card.append(el('header', {}, title, del));

      const grid = el('div', { className: 'grid' });
      const redraw = () => {
        title.textContent = `${section.itemLabel} ${idx + 1}${name() ? ` — ${name()}` : ''}`;
        if (section.id === 'services') redrawMasters();
      };
      section.fields.filter((f) => visible(f, item)).forEach((f) => {
        const wrap = renderField(f, item, redraw);
        if (!wrap) return;
        // Код услуги правят руками — ссылки на неё ведём следом. Ждём sl-change:
        // по каждому нажатию клавиши переносить нельзя, промежуточный код может
        // совпасть с кодом соседней услуги и утащить чужие привязки.
        if (section.id === 'services' && f.key === section.idField) {
          let prev = item.id;
          wrap.addEventListener('sl-change', () => {
            const next = item.id;
            if (prev && next && prev !== next) {
              mapServiceRefs((list) => list.map((sid) => (sid === prev ? next : sid)));
              redrawMasters();
            }
            prev = next;
          });
        }
        // Название меняется — обновляем заголовок карточки на лету.
        // Событие Shoelace всплывает, поэтому хватает одного слушателя на поле.
        wrap.addEventListener('sl-input', redraw);
        grid.append(wrap);
      });
      card.append(grid);
      // Привязка чата и календарь — не поля формы: их ставят кнопки, минуя сохранение.
      if (section.id === 'masters') {
        const calendar = masterCalendarBlock(item);
        if (calendar) card.append(calendar);
        card.append(masterTelegramBlock(item));
        card.append(masterCabinetBlock(item));
      }
      box.append(card);
    });

    const add = el('button', { className: 'btn-add', type: 'button' },
      icon('plus', { size: 16 }), `Добавить ${addLabel(section.itemLabel)}`);
    add.onclick = () => {
      const fresh = {};
      section.fields.forEach((f) => { if (f.default !== undefined) fresh[f.key] = f.default; });
      items.push(fresh);
      draw();
      if (section.id === 'services') redrawMasters();
      box.querySelector('.item:last-of-type input')?.focus();
    };
    box.append(add);
  };

  draw();
  return box;
}

/** Пройти по всем полям-ссылкам на услуги (услуги мастера, «предлагать вместе»). */
function mapServiceRefs(fn) {
  (schema?.sections ?? []).forEach((section) => {
    const refs = section.fields.filter((f) => f.type === 'serviceRefs');
    if (!refs.length) return;
    const scopes = section.kind === 'object' ? [data[section.id] ?? {}] : (data[section.id] ?? []);
    scopes.forEach((scope) => refs.forEach((f) => {
      const list = get(scope, f.key);
      if (Array.isArray(list)) set(scope, f.key, fn(list));
    }));
  });
}

function redrawMasters() {
  const old = document.querySelector('[data-section="masters"]');
  if (!old) return;
  old.replaceWith(renderListSection(schema.sections.find((s) => s.id === 'masters')));
}

/* ======================= КАЛЕНДАРЬ МАСТЕРА ============================= */
/* Новый мастер заводится с `calendarId: "primary"` — основным календарём
   подключённого аккаунта. Пока салон в локальном режиме это незаметно:
   занятость считается по своей базе, по коду мастера. После подключения Google
   двое на одном календаре видят чужие события как свою занятость — салон молча
   теряет половину окон, и выясняется это по жалобам клиентов, а не в панели.
   Поэтому: предупреждение всегда и кнопка «Создать календарь», когда есть чем
   его создать. */

const calendarKey = (m) => ((m.calendarId || '').trim() || 'primary');

/** Мастера, у которых тот же календарь, что и у этого. */
function calendarTwins(item) {
  const key = calendarKey(item);
  return (data?.masters ?? []).filter((m) => m !== item && calendarKey(m) === key);
}

function masterCalendarBlock(item) {
  const twins = calendarTwins(item);
  const connected = current()?.calendarMode === 'google';
  // Молчим, когда сказать нечего: у мастера свой календарь и он единственный.
  if (!twins.length && (!connected || calendarKey(item) !== 'primary')) return null;

  const box = el('div', { className: `connect connect-sm${twins.length ? ' warn' : ''}` });
  const body = el('div', { className: 'body' });
  const names = twins.map((m) => m.name || m.id).filter(Boolean).join(', ');

  if (twins.length) {
    body.append(el('b', {}, 'Общий календарь'),
      el('span', {}, connected
        ? `Тот же календарь, что у ${names}. Их записи занимают время друг друга — `
          + 'мастер выглядит занятым, когда он свободен.'
        : `Тот же календарь, что у ${names}. Пока записи считаются по своей базе, `
          + 'но после подключения Google они начнут занимать время друг друга.'));
  } else {
    body.append(el('b', {}, 'Основной календарь аккаунта'),
      el('span', {}, 'Записи мастера попадают в общий календарь салона. '
        + 'Отдельный календарь удобнее: его можно расшарить самому мастеру.'));
  }

  const nodes = [el('div', { className: 'icon' }, icon(twins.length ? 'warning' : 'calendar', { size: 18 })), body];
  if (connected) {
    const make = el('button', { className: 'btn btn-primary btn-sm', type: 'button' },
      icon('plus', { size: 15 }), 'Создать календарь');
    make.onclick = () => createMasterCalendar(make, item);
    nodes.push(make);
  } else {
    body.append(el('span', {}, 'Создать отдельный календарь можно после подключения Google.'));
  }
  box.replaceChildren(...nodes);
  return box;
}

async function createMasterCalendar(btn, item) {
  const id = (item.id || '').trim();
  if (!id) {
    toast('warn', 'Сначала код мастера', 'Задайте код и дождитесь сохранения настроек.');
    return;
  }
  btn.disabled = true;
  try {
    const res = await api(url(`/api/admin/masters/${encodeURIComponent(id)}/calendar`), {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: '' }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      toast('err', 'Календарь не создан', payload.detail || 'Сервер отклонил запрос.');
      btn.disabled = false;
      return;
    }
    // Сервер уже записал ID в salon.json — здесь только подтягиваем форму,
    // иначе следующее автосохранение вернуло бы «primary» обратно.
    googleCalendars = payload.calendars ?? googleCalendars;
    item.calendarId = payload.calendarId;
    redrawMasters();
    toast('ok', 'Календарь создан', payload.title);
  } catch {
    toast('err', 'Календарь не создан', 'Не удалось связаться с сервером.');
    btn.disabled = false;
  }
}

/* ======================= TELEGRAM МАСТЕРАМ ============================= */
/* Мастеру уходят только его записи. Различает мастеров код в ссылке
   t.me/бот?start=<код>, а не «кто написал последним»: двое нажали «Начать»
   подряд — и обоим приходили бы чужие клиенты. Ссылку владелец пересылает
   мастеру сам: у панели нет способа написать человеку, которого в ней нет. */

let masterTgState = null;   // карточек много, а состояние одно — запрос тоже

function masterTelegram(force = false) {
  if (!masterTgState || force) {
    masterTgState = apiJson(url('/api/admin/telegram/masters')).catch(() => null);
  }
  return masterTgState;
}

function masterTelegramBlock(item) {
  const box = el('div', { className: 'connect connect-sm' });
  drawMasterTelegram(box, item);
  return box;
}

async function drawMasterTelegram(box, item) {
  const id = (item.id || '').trim();
  const redraw = () => drawMasterTelegram(box, item);
  const state = await masterTelegram();
  const body = el('div', { className: 'body' });
  const ico = (name) => el('div', { className: 'icon' }, icon(name, { size: 18 }));
  box.className = 'connect connect-sm';

  if (!state) {
    body.append(el('b', {}, 'Telegram мастера'), el('span', {}, 'Не удалось проверить подключение.'));
    box.replaceChildren(ico('warning'), body);
    return;
  }
  if (!state.botConnected) {
    body.append(el('b', {}, 'Telegram мастера'),
      el('span', {}, 'Сначала подключите бота салона — вкладка «Передача администратору».'));
    box.replaceChildren(ico('send'), body);
    return;
  }

  // Мастера, которого ещё не сохранили, на сервере нет — и ссылки для него тоже.
  const known = state.masters.find((m) => m.id === id);
  if (!known) {
    body.append(el('b', {}, 'Telegram мастера'),
      el('span', {}, id ? 'Сохраните настройки — тогда появится ссылка для привязки.'
                        : 'Задайте код мастера и сохраните настройки.'));
    box.replaceChildren(ico('info'), body);
    return;
  }

  if (known.connected) {
    box.className = 'connect connect-sm linked';
    body.append(el('b', {}, 'Telegram привязан'),
      el('span', {}, 'Приходят новые записи и отмены — только собственные.'));
    const test = el('button', { className: 'btn btn-primary btn-sm', type: 'button' },
      icon('send', { size: 15 }), 'Отправить тест');
    test.onclick = () => testMasterTelegram(test, id);
    const off = el('button', { className: 'btn btn-ghost btn-sm', type: 'button', textContent: 'Отвязать' });
    off.onclick = () => unlinkMasterTelegram(known.name, id, redraw);
    box.replaceChildren(ico('checkCircle'), body, test, off);
    return;
  }

  body.append(el('b', {}, 'Telegram не привязан'),
    el('span', {}, 'Отправьте мастеру ссылку. Он откроет её и нажмёт «Начать» — после этого «Проверить».'));
  const copy = el('button', { className: 'btn btn-secondary btn-sm', type: 'button' },
    icon('copy', { size: 15 }), 'Скопировать ссылку');
  copy.onclick = () => copyMasterLink(known.link);
  const check = el('button', { className: 'btn btn-primary btn-sm', type: 'button' },
    icon('checkCircle', { size: 15 }), 'Проверить');
  check.onclick = () => linkMasterTelegram(check, known.name, id, redraw);
  box.replaceChildren(ico('send'), body, copy, check);
}

async function copyMasterLink(link) {
  try {
    await navigator.clipboard.writeText(link);
    toast('ok', 'Ссылка скопирована', 'Отправьте её мастеру — в Telegram, WhatsApp, как удобно.');
  } catch {
    // Буфер недоступен без https или без разрешения — показываем саму ссылку,
    // иначе кнопка просто молчит и владелец не понимает, сработала ли она.
    toast('info', 'Скопируйте ссылку вручную', link, { timeout: 20000 });
  }
}

async function linkMasterTelegram(btn, name, id, done) {
  btn.disabled = true;
  try {
    const res = await api(url(`/api/admin/telegram/masters/${encodeURIComponent(id)}/link`), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Чат не найден');
    toast('ok', 'Чат привязан', `Записи мастера ${name} уходят в «${payload.chatTitle || payload.chatId}».`);
    await masterTelegram(true);
    done?.();
    // Сервер записал чат мимо формы: без перечитывания автосохранение вернёт
    // карточку мастера целиком — вместе с календарём, каким он был до этого.
    await load();
  } catch (e) {
    toast('err', 'Чат не привязан', e.message || 'Попросите мастера открыть ссылку и нажать «Начать».',
      { timeout: 12000 });
  } finally {
    btn.disabled = false;
  }
}

async function testMasterTelegram(btn, id) {
  btn.disabled = true;
  try {
    const res = await api(url(`/api/admin/telegram/masters/${encodeURIComponent(id)}/test`), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Сообщение не ушло');
    toast('ok', 'Сообщение отправлено', 'Мастер должен увидеть его в чате с ботом.');
  } catch (e) {
    toast('err', 'Сообщение не ушло', e.message || 'Telegram отклонил запрос.');
  } finally {
    btn.disabled = false;
  }
}

async function unlinkMasterTelegram(name, id, done) {  // eslint-disable-line
  const ok = await confirmDialog({
    title: `Отвязать Telegram у ${name}?`,
    message: 'Мастер перестанет получать свои записи и отмены. Записи и расписание не меняются — '
      + 'привязать чат заново можно в любой момент.',
    confirmLabel: 'Отвязать', danger: true,
  });
  if (!ok) return;
  await api(url(`/api/admin/telegram/masters/${encodeURIComponent(id)}/unlink`), { method: 'POST' });
  toast('ok', 'Telegram отвязан', `${name} больше не получает уведомлений.`);
  await masterTelegram(true);
  done?.();
}

/* ========================= КАБИНЕТ МАСТЕРА ============================= */
/* Мастеру не нужна панель: здесь выручка салона, клиентская база и ключи. Ему
   нужен свой день и свой график — для этого есть отдельный адрес и личная
   ссылка. Ссылку показываем один раз: в базе лежит только её хеш, и «покажите
   ещё раз» честно означает «выдайте новую». */

let masterAccessState = null;   // карточек много, а состояние одно — запрос тоже

function masterAccess(force = false) {
  if (!masterAccessState || force) {
    masterAccessState = apiJson(url('/api/admin/masters/access')).catch(() => null);
  }
  return masterAccessState;
}

function masterCabinetBlock(item) {
  const box = el('div', { className: 'connect connect-sm' });
  drawMasterCabinet(box, item);
  return box;
}

async function drawMasterCabinet(box, item) {
  const id = (item.id || '').trim();
  const redraw = () => drawMasterCabinet(box, item);
  const state = await masterAccess();
  const body = el('div', { className: 'body' });
  const ico = (name) => el('div', { className: 'icon' }, icon(name, { size: 18 }));
  box.className = 'connect connect-sm';

  if (!state) {
    body.append(el('b', {}, 'Кабинет мастера'), el('span', {}, 'Не удалось проверить доступ.'));
    box.replaceChildren(ico('warning'), body);
    return;
  }
  const known = state.masters.find((m) => m.id === id);
  if (!known) {
    body.append(el('b', {}, 'Кабинет мастера'),
      el('span', {}, id ? 'Сохраните настройки — тогда появится ссылка в кабинет.'
                        : 'Задайте код мастера и сохраните настройки.'));
    box.replaceChildren(ico('info'), body);
    return;
  }

  const issue = el('button', { className: 'btn btn-primary btn-sm', type: 'button' },
    icon('link', { size: 15 }), known.issued ? 'Выдать заново' : 'Выдать ссылку');
  issue.onclick = () => issueMasterCabinet(issue, known.name, id, redraw);

  if (known.issued) {
    box.className = 'connect connect-sm linked';
    const seen = known.lastSeenAt
      ? `Заходил: ${new Date(known.lastSeenAt).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}.`
      : 'Ещё ни разу не заходил.';
    // «ПИН ещё не задан» у мастера, который уверяет, что вошёл, означает, что
    // ссылку открыл кто-то другой. Поэтому состояние видно, а сам ПИН — нет.
    const pin = known.pinSet ? 'ПИН задан мастером.' : 'ПИН ещё не задан — задаст при первом входе.';
    // Блокировка после промахов — первое, что объясняет «у меня не
    // открывается»: без этой строки владелец разбирался бы вслепую.
    const locked = known.lockedUntil
      ? ` Вход закрыт до ${new Date(known.lockedUntil).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })} — ПИН вводили неверно.`
      : '';
    body.append(el('b', {}, 'Доступ в кабинет открыт'),
      el('span', {}, `${seen} ${pin}${locked}`));

    const buttons = [issue];
    if (known.pinSet || known.lockedUntil) {
      const reset = el('button', { className: 'btn btn-secondary btn-sm', type: 'button' },
        icon('refresh', { size: 15 }), 'Сбросить ПИН');
      reset.onclick = () => resetMasterPin(reset, known.name, id, redraw);
      buttons.push(reset);
    }
    const off = el('button', { className: 'btn btn-ghost btn-sm', type: 'button', textContent: 'Закрыть доступ' });
    off.onclick = () => revokeMasterCabinet(known.name, id, redraw);
    buttons.push(off);
    box.replaceChildren(ico('checkCircle'), body, ...buttons);
    return;
  }

  body.append(el('b', {}, 'Кабинет не открыт'),
    el('span', {}, 'Выдайте личную ссылку и отправьте мастеру. ПИН он придумает сам при первом входе — вам его знать не нужно.'));
  box.replaceChildren(ico('link'), body, issue);
}

async function issueMasterCabinet(btn, name, id, done) {
  if (btn.dataset.busy) return;
  btn.dataset.busy = '1';
  btn.disabled = true;
  try {
    const res = await api(url(`/api/admin/masters/${encodeURIComponent(id)}/access`), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Ссылку выдать не удалось');
    await masterAccess(true);
    done?.();
    // Ссылку показываем целиком и надолго: второй раз её взять неоткуда — в
    // базе только хеш. В буфер кладём молча: сообщение и так на экране.
    let copied = false;
    try {
      await navigator.clipboard.writeText(payload.link);
      copied = true;
    } catch {
      copied = false;   // буфер недоступен без https или без разрешения
    }
    toast('ok', `Ссылка для ${name} готова`,
      `${payload.link}\n\n${copied ? 'Скопирована в буфер. ' : ''}`
      + 'Отправьте её мастеру: ПИН он придумает сам при первом входе. Показать ссылку '
      + 'ещё раз нельзя — если потеряется, выдайте новую.', { timeout: 60000 });
  } catch (e) {
    toast('err', 'Ссылка не выдана', e.message || 'Не удалось связаться с сервером.');
  } finally {
    delete btn.dataset.busy;
    btn.disabled = false;
  }
}

async function resetMasterPin(btn, name, id, done) {
  const ok = await confirmDialog({
    title: `Сбросить ПИН у ${name}?`,
    message: 'Ссылка останется прежней — мастер задаст новый ПИН при следующем входе. '
      + 'Открытые кабинеты на его телефоне продолжают работать: сброс нужен тому, кто цифры забыл.',
    confirmLabel: 'Сбросить',
  });
  if (!ok) return;
  btn.disabled = true;
  try {
    await api(url(`/api/admin/masters/${encodeURIComponent(id)}/access/pin`), { method: 'POST' });
    await masterAccess(true);
    done?.();
    toast('ok', 'ПИН сброшен', `${name} придумает новый, когда откроет свою ссылку.`);
  } catch (e) {
    toast('err', 'ПИН не сброшен', e.message || 'Не удалось связаться с сервером.');
  } finally {
    btn.disabled = false;
  }
}

async function revokeMasterCabinet(name, id, done) {
  const ok = await confirmDialog({
    title: `Закрыть кабинет у ${name}?`,
    message: 'Ссылка перестанет работать сразу, вместе с уже открытыми кабинетами на телефоне. '
      + 'Записи и график не меняются — выдать доступ заново можно в любой момент.',
    confirmLabel: 'Закрыть доступ', danger: true,
  });
  if (!ok) return;
  await api(url(`/api/admin/masters/${encodeURIComponent(id)}/access`), { method: 'DELETE' });
  await masterAccess(true);
  done?.();
  toast('ok', 'Доступ закрыт', `${name} больше не откроет кабинет по старой ссылке.`);
}

/* ============================== ЗАПИСИ ================================== */

const STATUS = {
  confirmed: { label: 'подтверждена', icon: 'clock' },
  completed: { label: 'пришёл', icon: 'checkCircle' },
  no_show: { label: 'не пришёл', icon: 'warning' },
  cancelled: { label: 'отменена', icon: 'x' },
};
const statusMeta = (s) => STATUS[s] ?? { label: s, icon: 'info' };

/** Статус: цвет плюс значок плюс текст — только цветом состояние не обозначаем. */
function statusBadge(booking) {
  if (booking.requiresConfirmation && !booking.confirmedByClient && booking.status === 'confirmed') {
    return el('span', { className: 'badge pending' }, icon('alert', { size: 12 }), 'ждёт подтверждения');
  }
  const m = statusMeta(booking.status);
  return el('span', { className: `badge ${booking.status}` }, icon(m.icon, { size: 12 }), m.label);
}

const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

/* Время показываем в поясе салона, а не браузера: владелец может открыть панель
   из отпуска, а визит остаётся в том часе, на который записан клиент. Сервер
   отдаёт момент с поясом — здесь он только переводится в местное время салона. */
const salonZone = () => data?.salon?.timezone || undefined;

const fmtDate = (iso) => new Date(iso).toLocaleDateString('ru-RU',
  { day: '2-digit', month: 'short', weekday: 'short', timeZone: salonZone() });
const fmtTime = (iso) => new Date(iso).toLocaleTimeString('ru-RU',
  { hour: '2-digit', minute: '2-digit', timeZone: salonZone() });
/** Дата в поясе салона — по ней фильтруются записи, и у полуночи это разные дни. */
const dateKey = (iso) => new Date(iso).toLocaleDateString('en-CA', { timeZone: salonZone() });

const bookingsState = {
  all: [], query: '', date: '', master: '', service: '', status: '',
  sort: { key: 'start', dir: 'desc' }, page: 1,
};

async function renderBookings(panel) {
  const head = pageHead('Записи', 'Все визиты салона: созданные ботом, виджетом и вручную.');
  const newBtn = el('button', { className: 'btn btn-primary' }, icon('plus', { size: 16 }), 'Новая запись');
  newBtn.onclick = openNewBooking;
  head.querySelector('.tools').append(newBtn);

  const body = el('div', {});
  panel.replaceChildren(head, body);
  body.append(skeletonCards(4), skeletonTable());

  try {
    const res = await apiData(url('/api/admin/bookings?limit=500'));
    bookingsState.all = res.bookings ?? [];
    bookingsState.page = 1;
    drawBookings(body);
  } catch (err) {
    body.replaceChildren(errorState(
      'Не удалось загрузить записи', loadFailure(err),
      () => renderBookings(panel)));
  }
}

/** Фильтрация и сортировка идут по загруженному списку — без лишних запросов. */
function filteredBookings() {
  const s = bookingsState;
  const q = s.query.trim().toLowerCase();
  const rows = s.all.filter((b) => {
    if (q && !(`${b.client} ${b.phone}`.toLowerCase().includes(q))) return false;
    if (s.date && dateKey(b.start) !== s.date) return false;
    if (s.master && b.masterId !== s.master) return false;
    if (s.service && b.serviceId !== s.service) return false;
    if (s.status && b.status !== s.status) return false;
    return true;
  });
  const { key, dir } = s.sort;
  const sign = dir === 'asc' ? 1 : -1;
  return rows.sort((a, b) => {
    const av = key === 'start' ? new Date(a.start).getTime() : String(a[key] ?? '').toLowerCase();
    const bv = key === 'start' ? new Date(b.start).getTime() : String(b[key] ?? '').toLowerCase();
    return av < bv ? -sign : av > bv ? sign : 0;
  });
}

function drawBookings(body) {
  const s = bookingsState;
  const rows = filteredBookings();
  const today = dateKey(new Date().toISOString());
  const now = Date.now();

  const tiles = [
    { label: 'Сегодня', value: s.all.filter((b) => dateKey(b.start) === today && b.status !== 'cancelled').length,
      note: 'записей на сегодня', icon: 'calendar', cls: 'accent' },
    { label: 'Ожидают визита', value: s.all.filter((b) => b.status === 'confirmed' && new Date(b.start).getTime() >= now).length,
      note: 'подтверждены, впереди', icon: 'clock', cls: '' },
    { label: 'Завершено', value: s.all.filter((b) => b.status === 'completed').length,
      note: 'клиент пришёл', icon: 'checkCircle', cls: 'ok' },
    { label: 'Отменено', value: s.all.filter((b) => b.status === 'cancelled').length,
      note: 'снятые визиты', icon: 'x', cls: 'err' },
  ];
  const kpis = el('div', { className: 'kpis' }, ...tiles.map((t) => el('div', { className: `kpi ${t.cls}` },
    el('div', { className: 'kpi-top' }, icon(t.icon, { size: 14 }), el('span', { className: 'kpi-label' }, t.label)),
    el('b', {}, String(t.value)),
    el('small', {}, t.note))));

  body.replaceChildren(kpis, bookingFilters(body), bookingTable(rows, body));
}

function bookingFilters(body) {
  const s = bookingsState;
  const redraw = () => { s.page = 1; drawBookings(body); };

  const search = el('input', {
    type: 'search', value: s.query, placeholder: 'Имя клиента или телефон',
    attrs: { 'aria-label': 'Поиск по клиенту или телефону' },
  });
  let typing = null;
  search.oninput = () => {
    clearTimeout(typing);
    typing = setTimeout(() => { s.query = search.value; redraw(); }, 200);
  };

  const dateInput = el('input', {
    type: 'date', className: 'date-input', value: s.date,
    attrs: { 'aria-label': 'Фильтр по дате визита' },
  });
  dateInput.onchange = () => { s.date = dateInput.value; redraw(); };

  const pick = (label, value, options, onPick) => {
    const sel = el('select', { attrs: { 'aria-label': label } },
      el('option', { value: '', textContent: label }),
      ...options.map((o) => el('option', { value: o.value, textContent: o.label, selected: o.value === value })));
    sel.onchange = () => { onPick(sel.value); redraw(); };
    return sel;
  };

  const masters = [...new Map(s.all.map((b) => [b.masterId, b.master])).entries()]
    .map(([value, label]) => ({ value, label }));
  const services = [...new Map(s.all.map((b) => [b.serviceId, b.service])).entries()]
    .map(([value, label]) => ({ value, label }));

  const reset = el('button', { className: 'btn btn-ghost btn-sm' }, icon('filterOff', { size: 15 }), 'Сбросить');
  reset.onclick = () => {
    Object.assign(s, { query: '', date: '', master: '', service: '', status: '', page: 1 });
    drawBookings(body);
  };
  const anyFilter = s.query || s.date || s.master || s.service || s.status;
  reset.disabled = !anyFilter;

  const bar = el('div', { className: 'filters', attrs: { role: 'search' } },
    el('div', { className: 'search' }, icon('search', { size: 16 }), search),
    dateInput,
    pick('Все мастера', s.master, masters, (v) => { s.master = v; }),
    pick('Все услуги', s.service, services, (v) => { s.service = v; }),
    pick('Любой статус', s.status,
      Object.entries(STATUS).map(([value, m]) => ({ value, label: m.label })),
      (v) => { s.status = v; }),
    reset);

  // Flatpickr подключаем после вставки в DOM: он создаёт подменное поле рядом
  // с исходным, а элемент без родителя вставить некуда.
  if (window.flatpickr) {
    requestAnimationFrame(() => {
      if (!dateInput.isConnected || dateInput._flatpickr) return;
      dateInput.type = 'text';
      window.flatpickr(dateInput, {
        locale: 'ru', dateFormat: 'Y-m-d', altInput: true, altFormat: 'j F Y',
        defaultDate: s.date || null, allowInput: false,
        onChange: ([d]) => { s.date = d ? dateKey(d.toISOString()) : ''; redraw(); },
      });
      dateInput._flatpickr?.altInput?.setAttribute('aria-label', 'Фильтр по дате визита');
      dateInput._flatpickr?.altInput?.classList.add('date-input');
      if (!s.date) dateInput._flatpickr.altInput.placeholder = 'Дата визита';
    });
  }
  return bar;
}

const COLUMNS = [
  { key: 'start', label: 'Когда', sortable: true },
  { key: 'client', label: 'Клиент', sortable: true },
  { key: 'phone', label: 'Телефон', sortable: false },
  { key: 'service', label: 'Услуга', sortable: true },
  { key: 'master', label: 'Мастер', sortable: true },
  { key: 'status', label: 'Статус', sortable: true },
  { key: 'actions', label: '', sortable: false },
];

function bookingTable(rows, body) {
  const s = bookingsState;
  if (!s.all.length) {
    const add = el('button', { className: 'btn btn-primary' }, icon('plus', { size: 16 }), 'Новая запись');
    add.onclick = openNewBooking;
    return el('div', { className: 'table-wrap' }, emptyState('inbox', 'Записей пока нет',
      'Как только клиент запишется через виджет или бота, визит появится здесь.', add));
  }
  if (!rows.length) {
    const reset = el('button', { className: 'btn btn-secondary' }, icon('filterOff', { size: 15 }), 'Сбросить фильтры');
    reset.onclick = () => {
      Object.assign(s, { query: '', date: '', master: '', service: '', status: '', page: 1 });
      drawBookings(body);
    };
    return el('div', { className: 'table-wrap' }, emptyState('search', 'Ничего не найдено',
      'Под выбранные фильтры не подходит ни одна запись.', reset));
  }

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  s.page = Math.min(s.page, pages);
  const slice = rows.slice((s.page - 1) * PAGE_SIZE, s.page * PAGE_SIZE);

  const head = el('tr', {}, ...COLUMNS.map((c) => {
    const sorted = s.sort.key === c.key;
    const th = el('th', {
      className: c.sortable ? 'sortable' : '',
      attrs: { scope: 'col', ...(sorted ? { 'aria-sort': s.sort.dir === 'asc' ? 'ascending' : 'descending' } : {}) },
    });
    if (c.key === 'actions') { th.append(el('span', { className: 'sr-only' }, 'Действия')); return th; }
    th.append(c.label);
    if (c.sortable) {
      th.append(icon(sorted ? (s.sort.dir === 'asc' ? 'sortAsc' : 'sortDesc') : 'sort', { size: 12, cls: 'sort-ico' }));
      th.tabIndex = 0;
      const flip = () => {
        s.sort = { key: c.key, dir: sorted && s.sort.dir === 'desc' ? 'asc' : 'desc' };
        drawBookings(body);
      };
      th.onclick = flip;
      th.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); } };
    }
    return th;
  }));

  const tbody = el('tbody');
  slice.forEach((b) => {
    const openRow = () => openBookingDrawer(b, body);
    const tr = el('tr', { tabIndex: 0 });
    tr.onclick = (e) => { if (!e.target.closest('a, button')) openRow(); };
    tr.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); openRow(); } };
    tr.setAttribute('aria-label', `Запись: ${b.client}, ${fmtDate(b.start)} ${fmtTime(b.start)}`);

    const more = el('button', {
      className: 'btn btn-icon', attrs: { 'aria-label': `Действия по записи ${b.client}` },
    }, icon('more', { size: 17 }));

    tr.append(
      el('td', { dataset: { col: 'when' }, className: 'cell-when' },
        el('b', {}, fmtTime(b.start)), el('small', {}, fmtDate(b.start))),
      el('td', { dataset: { col: 'client' } }, b.client),
      el('td', { dataset: { col: 'phone' } },
        el('a', { className: 'phone', href: `tel:${b.phone}` }, b.phone)),
      el('td', { dataset: { col: 'service' } }, b.service),
      el('td', { dataset: { col: 'master' } },
        el('span', { className: 'cell-who' },
          el('span', { className: 'avatar', attrs: { 'aria-hidden': 'true' } }, initials(b.master)),
          b.master)),
      el('td', { dataset: { col: 'status' } }, statusBadge(b)),
      el('td', { dataset: { col: 'actions' }, className: 'actions' },
        actionMenu(more, rowActions(b, body))),
    );
    tbody.append(tr);
  });

  const prev = el('button', { className: 'btn btn-icon', attrs: { 'aria-label': 'Предыдущая страница' } },
    icon('chevronLeft', { size: 17 }));
  const next = el('button', { className: 'btn btn-icon', attrs: { 'aria-label': 'Следующая страница' } },
    icon('chevronRight', { size: 17 }));
  prev.disabled = s.page <= 1;
  next.disabled = s.page >= pages;
  prev.onclick = () => { s.page -= 1; drawBookings(body); };
  next.onclick = () => { s.page += 1; drawBookings(body); };

  return el('div', { className: 'table-wrap' },
    el('div', { className: 'table-scroll' },
      el('table', { className: 'data' }, el('thead', {}, head), tbody)),
    el('div', { className: 'table-foot' },
      el('span', { className: 'count' }, `Показано ${slice.length} из ${rows.length}`),
      el('div', { className: 'pager' }, prev,
        el('span', { className: 'page-of' }, `${s.page} / ${pages}`), next)));
}

/** Действия строки — в меню «•••»: три кнопки в каждой строке превращают таблицу в шум. */
function rowActions(b, body) {
  const change = (next, label, danger = false) => ({
    label, icon: statusMeta(next).icon, danger,
    disabled: b.status === next,
    onSelect: () => setBookingStatus(b, next, body),
  });
  return [
    { label: 'Открыть карточку', icon: 'external', onSelect: () => openBookingDrawer(b, body) },
    change('completed', 'Отметить визит'),
    change('no_show', 'Не пришёл'),
    change('cancelled', 'Отменить запись', true),
  ];
}

async function setBookingStatus(b, next, body) {
  if (next === 'cancelled') {
    const ok = await confirmDialog({
      title: 'Отменить запись?',
      message: `${b.client}, ${fmtDate(b.start)} в ${fmtTime(b.start)}. Событие удалится из календаря мастера, `
        + 'а будущие напоминания клиенту будут сняты.',
      confirmLabel: 'Отменить запись', cancelLabel: 'Оставить', danger: true,
    });
    if (!ok) return;
  }
  try {
    const res = await apiJson(url(`/api/admin/bookings/${b.id}/status`), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: next }),
    });
    b.status = res.status;
    drawBookings(body);
    toast('ok', 'Статус обновлён', `${b.client} — ${statusMeta(res.status).label}`);
    if (next === 'no_show' && res.limit && res.noShowCount >= res.limit) {
      toast('warn', `У клиента ${res.noShowCount} неявки`,
        'Бот попросит подтвердить следующий визит заранее.');
    }
  } catch {
    toast('err', 'Не удалось изменить статус', 'Запись осталась в прежнем состоянии.');
  }
}

/** Карточка записи: всё, что о ней известно, и действия — в одном месте. */
function openBookingDrawer(b, body) {
  const d = drawer({
    title: b.client,
    subtitle: `${fmtDate(b.start)} · ${fmtTime(b.start)}–${fmtTime(b.end)}`,
  });

  const sourceLabel = { web: 'веб-виджет на сайте', whatsapp: 'WhatsApp', admin: 'создана в панели' };
  const calendarRow = b.eventId
    ? el('span', { className: 'badge completed' }, icon('checkCircle', { size: 12 }), 'событие создано')
    : el('span', { className: 'badge no_show' }, icon('warning', { size: 12 }), 'события нет');

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Визит'),
      el('dl', { className: 'dl' },
        el('dt', {}, 'Статус'), el('dd', {}, statusBadge(b)),
        el('dt', {}, 'Услуга'), el('dd', {}, b.service),
        el('dt', {}, 'Мастер'), el('dd', {},
          el('span', { className: 'cell-who' },
            el('span', { className: 'avatar', attrs: { 'aria-hidden': 'true' } }, initials(b.master)), b.master)),
        el('dt', {}, 'Дата'), el('dd', {}, fmtDate(b.start)),
        el('dt', {}, 'Время'), el('dd', {}, `${fmtTime(b.start)} – ${fmtTime(b.end)}`))),

    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Клиент'),
      el('dl', { className: 'dl' },
        el('dt', {}, 'Имя'), el('dd', {}, b.client),
        el('dt', {}, 'Телефон'), el('dd', {}, el('a', { className: 'phone', href: `tel:${b.phone}` }, b.phone)),
        el('dt', {}, 'Уведомления'), el('dd', {}, b.notifyConsent ? 'согласие получено' : 'клиент отказался'),
        el('dt', {}, 'Язык'), el('dd', {}, (b.lang || 'ru').toUpperCase()),
        el('dt', {}, 'Группа'), el('dd', {}, `${b.groupSize || 1} мест`))),

    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Оплата'),
      el('dl', { className: 'dl' },
        el('dt', {}, 'Цена'), el('dd', {}, `${b.priceAmount || 0} ${b.currency || 'UYU'}`),
        el('dt', {}, 'Скидка'), el('dd', {}, `${b.discountAmount || 0} ${b.currency || 'UYU'}`),
        el('dt', {}, 'Оплачено'), el('dd', {}, paidLabel(b)),
        el('dt', {}, 'Способ'), el('dd', {}, PAYMENT_METHODS[b.paymentMethod] || b.paymentMethod || 'не отмечен'),
        el('dt', {}, 'Промокод'), el('dd', {}, b.promoCode || '—'))),

    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Происхождение'),
      el('dl', { className: 'dl' },
        el('dt', {}, 'Источник'), el('dd', {}, b.source || sourceLabel[b.channel] || 'неизвестен'),
        el('dt', {}, 'Создана'), el('dd', {}, `${fmtDate(b.createdAt)}, ${fmtTime(b.createdAt)}`),
        el('dt', {}, 'Календарь'), el('dd', {}, calendarRow),
        ...(b.htmlLink
          ? [el('dt', {}, 'Событие'), el('dd', {},
              el('a', { href: b.htmlLink, target: '_blank', rel: 'noopener', className: 'phone' },
                'Открыть в Google Calendar'))]
          : []))),

    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Комментарий клиента'),
      el('p', { className: 'note' }, b.comment || 'Клиент не оставил комментарий.')),
  );

  const act = (label, next, cls = 'btn-secondary') => {
    const btn = el('button', { className: `btn ${cls}` }, icon(statusMeta(next).icon, { size: 15 }), label);
    btn.disabled = b.status === next;
    btn.onclick = async () => { d.close(); await setBookingStatus(b, next, body); };
    return btn;
  };
  d.footer.append(
    act('Отметить визит', 'completed', 'btn-primary'),
    el('button', { className: 'btn btn-secondary', onclick: () => { d.close(); openRescheduleBooking(b, body); } },
      icon('clock', { size: 15 }), 'Перенести'),
    el('button', { className: 'btn btn-secondary', onclick: () => { d.close(); openPaymentBooking(b, body); } },
      icon('card', { size: 15 }), 'Оплата'),
    act('Не пришёл', 'no_show'),
    act('Отменить', 'cancelled', 'btn-ghost'),
  );
}

/** Перенос: выбираем из свободных окон, а не набираем время руками.

    Поле «время» показывало любую минуту дня, и занятое от свободного ничем не
    отличалось: администратор узнавал о занятости из отказа сервера уже после
    «Перенести». Окна берём с сервера — те же, что видит клиент, — а время
    самой переносимой записи остаётся в списке: перенос «на полчаса позже»
    начинается с того места, где запись стоит сейчас. */
function openRescheduleBooking(b, body) {
  const d = drawer({ title: 'Перенести запись', subtitle: `${b.client} · ${b.service}` });
  const master = el('select', {}, ...(data.masters || []).filter((m) => (m.services || []).includes(b.serviceId))
    .map((m) => el('option', { value: m.id, textContent: m.name || m.id })));
  master.value = b.masterId;
  const date = el('input', { type: 'date', value: dateKey(b.start) });
  const slotBox = el('div', { className: 'chips' });
  const state = { time: '' };

  const loadSlots = async () => {
    state.time = '';
    slotBox.replaceChildren(el('small', {}, 'Загружаю свободные окна…'));
    if (!master.value || !date.value) {
      slotBox.replaceChildren(el('small', {}, 'Выберите мастера и дату.'));
      return;
    }
    try {
      const payload = await apiData(url(`/api/admin/bookings/${b.id}/slots`
        + `?masterId=${encodeURIComponent(master.value)}&date=${date.value}`));
      const slots = payload.slots || [];
      if (!slots.length) {
        slotBox.replaceChildren(el('small', {}, 'На эту дату свободных окон нет.'));
        return;
      }
      const pick = (button, time) => {
        state.time = time;
        slotBox.querySelectorAll('button').forEach((x) => x.classList.replace('btn-primary', 'btn-secondary'));
        button.classList.replace('btn-secondary', 'btn-primary');
      };
      const buttons = slots.map((sl) => {
        const btn = el('button', { type: 'button', className: 'btn btn-secondary btn-sm', textContent: sl.time });
        btn.onclick = () => pick(btn, sl.time);
        return btn;
      });
      slotBox.replaceChildren(...buttons);
      // Время, где запись стоит сейчас, выделено сразу: видно, откуда двигаем.
      const here = slots.findIndex((sl) => sl.time === fmtTime(b.start));
      if (here >= 0 && date.value === dateKey(b.start) && master.value === b.masterId) {
        pick(buttons[here], slots[here].time);
      }
    } catch {
      slotBox.replaceChildren(el('small', {}, 'Не удалось получить расписание.'));
    }
  };

  master.onchange = loadSlots;
  date.onchange = loadSlots;

  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field' }, el('label', {}, 'Мастер'), master),
    el('div', { className: 'field' }, el('label', {}, 'Дата'), date),
    el('div', { className: 'field wide' }, el('label', {}, 'Свободное время'), slotBox)));
  loadSlots();

  const save = el('button', { className: 'btn btn-primary', textContent: 'Перенести' });
  save.onclick = async () => {
    if (!state.time) {
      toast('warn', 'Выберите время', 'Нужно свободное окно из списка.');
      return;
    }
    save.disabled = true;
    try {
      const res = await api(url(`/api/admin/bookings/${b.id}/reschedule`), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ masterId: master.value, date: date.value, time: state.time }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.detail || 'Не удалось перенести');
      d.close(); toast('ok', 'Запись перенесена', `${date.value} в ${state.time}`);
      await renderBookings(body.closest('[data-panel]') || body.parentElement);
    } catch (e) { toast('err', 'Запись не перенесена', e.message); }
    finally { save.disabled = false; }
  };
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена', onclick: d.close });
  d.footer.append(save, cancel);
}

const PAYMENT_METHODS = {
  cash: 'наличные', card: 'карта', transfer: 'перевод',
  certificate: 'сертификат', membership: 'абонемент',
};

/** Чем закрыт визит: деньгами или активом.

    Оплата абонементом не приносит денег в кассу — они пришли, когда абонемент
    продавали. Но «0 UYU» в карточке неотличимо от несохранённой оплаты, поэтому
    вместо суммы пишем код актива и остаток по нему. */
function paidLabel(b) {
  const money = `${b.paidAmount || 0} ${b.currency || 'UYU'}`;
  if (!b.assetId) return money;
  if (!b.assetCode) return `${money} · актив удалён`;
  const kind = b.assetKind === 'membership' ? 'абонементом' : 'сертификатом';
  const left = b.assetKind === 'membership'
    ? `осталось ${b.assetLeft ?? 0}`
    : `остаток ${b.assetLeft ?? 0} ${b.currency || 'UYU'}`;
  return `${kind} ${b.assetCode} · ${left}`;
}

/** Активы, которыми можно оплатить визит этого клиента.

    Чужие абонементы не показываем вовсе: сервер их и так отклонит, но выбор,
    который заведомо не сработает, — это ловушка для администратора. Сертификат
    без владельца остаётся в списке: он на предъявителя. */
async function loadClientAssets(clientId) {
  try {
    const rows = (await apiJson(url('/api/admin/assets'))).assets || [];
    return rows.filter((a) => a.status === 'active'
      && (!a.clientId || (clientId && a.clientId === clientId)));
  } catch {
    return [];
  }
}

async function openPaymentBooking(b, body) {
  const d = drawer({ title: 'Оплата визита', subtitle: `${b.client} · ${b.service}` });
  const amount = el('input', { type: 'number', min: 0, value: b.paidAmount || b.priceAmount || 0 });
  const discount = el('input', { type: 'number', min: 0, value: b.discountAmount || 0 });
  const loyalty = el('input', { type: 'number', min: 0, value: 0 });

  /* Абонемент и сертификат: продали заранее, тратят сейчас. Пока списания не
     было, «оплачено абонементом» и сам абонемент расходились с первого визита,
     и остаток правили руками.

     Деньги при этом остаются нулём намеренно — выручка признана при продаже
     абонемента, и второй раз в отчёт она попасть не должна. Поэтому в карточке
     пишем, чем оплачено и сколько осталось, а не «0 UYU»: ноль без объяснения
     выглядит как несохранённая оплата. */
  const assets = await loadClientAssets(b.clientId);
  const asset = el('select', {},
    el('option', { value: '', textContent: assets.length ? 'Не использовать' : 'Активов нет' }),
    ...assets.map((a) => el('option', {
      value: a.id,
      textContent: `${a.kind === 'membership' ? 'Абонемент' : 'Сертификат'} ${a.code}`
        + ` · ${a.kind === 'membership' ? `осталось ${a.uses}` : `${a.balance} ${b.currency || 'UYU'}`}`,
    })));
  asset.disabled = !assets.length;
  const method = el('select', {}, ...Object.entries(PAYMENT_METHODS).map(([value, label]) =>
    el('option', { value, textContent: label[0].toUpperCase() + label.slice(1) })));
  method.value = b.paymentMethod || 'cash';
  // Абонемент и баллы вместе сервер не принимает — делаем это видимым здесь,
  // а не отказом после нажатия «Сохранить».
  const byAsset = () => Boolean(asset.value);
  const sync = () => {
    amount.disabled = byAsset();
    method.disabled = byAsset();
    loyalty.disabled = byAsset();
    if (byAsset()) loyalty.value = 0;
    note.textContent = byAsset()
      ? 'Визит спишется с актива. Сумма и баллы не применяются: деньги учтены при его продаже.'
      : '';
  };
  const note = el('small', { className: 'slot-note' });
  asset.onchange = sync;

  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field' }, el('label', {}, `Оплачено, ${b.currency || 'UYU'}`), amount),
    el('div', { className: 'field' }, el('label', {}, 'Способ'), method),
    el('div', { className: 'field' }, el('label', {}, 'Скидка'), discount),
    el('div', { className: 'field' }, el('label', {}, 'Списать баллов'), loyalty),
    el('div', { className: 'field wide' }, el('label', {}, 'Абонемент или сертификат'), asset, note)));
  sync();
  const save = el('button', { className: 'btn btn-primary', textContent: 'Сохранить оплату' });
  save.onclick = async () => {
    save.disabled = true;
    try {
      // Вид актива решает сервер: панель не угадывает, абонемент это или
      // сертификат, — иначе способ оплаты в отчёте разойдётся с тем, чем платили.
      const payload0 = byAsset()
        ? { paidAmount: 0, paymentMethod: method.value, assetId: asset.value,
            discountAmount: Number(discount.value) }
        : { paidAmount: Number(amount.value), paymentMethod: method.value,
            discountAmount: Number(discount.value), loyaltyPoints: Number(loyalty.value) };
      const res = await api(url(`/api/admin/bookings/${b.id}/payment`), {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload0),
      });
      const payload = await res.json().catch(() => ({}));
      // Отказы сервера уже написаны по-человечески («осталось 1000, а визит
      // стоит 1500») — показываем их как есть, не подменяя своим текстом.
      if (!res.ok) throw new Error(payload.detail || 'Не удалось сохранить');
      d.close();
      if (byAsset()) {
        // Вид берём из самого актива, а не из ответа: если поле в ответе
        // изменится или пропадёт, подпись не должна тихо превращать абонемент
        // в сертификат.
        const used = assets.find((a) => a.id === asset.value);
        const kind = used?.kind || payload.method;
        toast('ok', 'Оплачено активом',
          `${used?.code || ''} · ${kind === 'membership' ? 'абонемент' : 'сертификат'}`);
      } else {
        toast('ok', 'Оплата сохранена', `${amount.value} ${b.currency || 'UYU'}`);
      }
      const panel = body.closest('[data-panel]'); if (panel) await renderBookings(panel);
    } catch (e) { toast('err', 'Оплата не сохранена', e.message); }
    finally { save.disabled = false; }
  };
  d.footer.append(save, el('button', { className: 'btn btn-ghost', textContent: 'Отмена', onclick: d.close }));
}

/** Ручная запись: тот же путь, что у виджета — свободные окна берём с сервера. */
/** «пн, 24 авг» из ключа даты — для подписей, где полная дата избыточна. */
const fmtDayLabel = (key) => {
  if (!key) return '';
  const d = fromKey(key);
  return `${WEEK_SHORT[weekIndex(key)].toLowerCase()}, ${d.getDate()} ${RU_MON_SHORT[d.getMonth()]}`;
};

async function openNewBooking(preset = {}) {
  const services = data.services ?? [];
  const masters = data.masters ?? [];
  if (!services.length || !masters.length) {
    toast('warn', 'Сначала заполните справочники', 'Нужна хотя бы одна услуга и один мастер.');
    return;
  }

  // Клик по пустому месту в журнале приходит сюда с мастером, датой и часом:
  // администратор уже показал пальцем, куда именно писать, и переспрашивать
  // его тремя полями подряд — это заставлять делать работу дважды.
  const d = drawer({
    title: 'Новая запись',
    subtitle: preset.time
      ? `${fmtDayLabel(preset.date)}, ${preset.time}${preset.masterName ? ` · ${preset.masterName}` : ''}`
      : 'Клиент позвонил или пришёл без записи',
  });
  const state = { serviceId: services[0].id, masterId: '', date: preset.date || '', start: '' };

  const serviceSel = el('select', {}, ...services.map((s) => el('option', { value: s.id, textContent: s.title || s.id })));
  const masterSel = el('select', {});
  const dateInput = el('input', { type: 'date', value: preset.date || '' });
  const slotBox = el('div', { className: 'chips' });
  const name = el('input', { type: 'text', placeholder: 'Имя клиента' });
  const phone = el('input', { type: 'text', placeholder: '+598 …' });
  const comment = el('textarea', { placeholder: 'Комментарий (необязательно)' });
  const consent = el('input', { type: 'checkbox', checked: true, id: 'nb-consent' });

  const fillMasters = () => {
    const fit = masters.filter((m) => (m.services ?? []).includes(state.serviceId));
    masterSel.replaceChildren(...fit.map((m) => el('option', { value: m.id, textContent: m.name || m.id })));
    // Мастера из клика держим, пока он делает выбранную услугу: иначе выбор
    // услуги молча перебрасывал бы запись на другого человека.
    const wanted = fit.some((m) => m.id === preset.masterId) ? preset.masterId : fit[0]?.id;
    state.masterId = wanted ?? '';
    masterSel.value = state.masterId;
    if (!fit.length) masterSel.append(el('option', { value: '', textContent: 'Нет мастера для услуги' }));
  };
  fillMasters();

  const loadSlots = async () => {
    slotBox.replaceChildren(el('small', {}, 'Загружаю свободные окна…'));
    state.start = '';
    if (!state.masterId || !state.date) {
      slotBox.replaceChildren(el('small', {}, 'Выберите мастера и дату.'));
      return;
    }
    try {
      const res = await fetch(url(`/api/slots?masterId=${encodeURIComponent(state.masterId)}`
        + `&serviceId=${encodeURIComponent(state.serviceId)}&date=${state.date}`));
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? 'ошибка');
      if (!body.slots?.length) {
        slotBox.replaceChildren(el('small', {}, 'На эту дату свободных окон нет.'));
        return;
      }
      const pick = (button, time) => {
        state.start = time;
        slotBox.querySelectorAll('button').forEach((x) => x.classList.replace('btn-primary', 'btn-secondary'));
        button.classList.replace('btn-secondary', 'btn-primary');
      };
      const buttons = body.slots.map((sl) => {
        const b = el('button', { type: 'button', className: 'btn btn-secondary btn-sm', textContent: sl.time });
        b.onclick = () => pick(b, sl.time);
        return b;
      });
      slotBox.replaceChildren(...buttons);

      // Кликнули в 14:15 при шаге слотов в полчаса — выбираем ближайшее
      // свободное и говорим об этом. Молча сдвинуть время нельзя: администратор
      // считает, что записал на то, куда ткнул.
      if (wanted.time) {
        const exact = body.slots.findIndex((sl) => sl.time === wanted.time);
        const near = exact >= 0 ? exact : body.slots.findIndex((sl) => sl.time > wanted.time);
        if (near >= 0) {
          pick(buttons[near], body.slots[near].time);
          if (exact < 0) {
            // «Занято» и «не по сетке» — разные вещи, и врать про первое нельзя:
            // в 14:07 никто не занят, просто окна идут через полчаса.
            const step = Number(data.salon?.slotStepMinutes || 30);
            const [h, m] = wanted.time.split(':').map(Number);
            const onGrid = (h * 60 + m) % step === 0;
            slotBox.append(el('small', { className: 'slot-note' }, onGrid
              ? `${wanted.time} занято — выбрано ближайшее свободное ${body.slots[near].time}.`
              : `Окна идут через ${step} мин — выбрано ближайшее ${body.slots[near].time}.`));
          }
        } else {
          slotBox.append(el('small', { className: 'slot-note' },
            `После ${wanted.time} свободных окон в этот день нет.`));
        }
        wanted.time = '';   // подсказка нужна один раз, а не при каждой смене услуги
      }
    } catch {
      slotBox.replaceChildren(el('small', {}, 'Не удалось получить расписание.'));
    }
  };

  const wanted = { time: preset.time || '' };

  serviceSel.onchange = () => { state.serviceId = serviceSel.value; fillMasters(); loadSlots(); };
  masterSel.onchange = () => { state.masterId = masterSel.value; loadSlots(); };
  dateInput.onchange = () => { state.date = dateInput.value; loadSlots(); };

  const field = (label, control, hint = '') => el('div', { className: 'field' },
    el('label', {}, label), control, hint ? el('small', {}, hint) : null);

  d.body.append(el('div', { className: 'grid' },
    field('Услуга', serviceSel),
    field('Мастер', masterSel),
    field('Дата', dateInput),
    el('div', { className: 'field wide' }, el('label', {}, 'Свободное время'), slotBox),
    field('Имя клиента', name),
    field('Телефон', phone),
    el('div', { className: 'field wide' }, el('label', {}, 'Комментарий'), comment),
    el('div', { className: 'field wide' },
      el('label', { className: 'switch', htmlFor: 'nb-consent' },
        consent, el('span', { className: 'track', attrs: { 'aria-hidden': 'true' } }),
        el('span', { className: 'switch-text' },
          el('span', {}, 'Присылать подтверждение и напоминания'),
          el('small', {}, 'Клиент согласился получать сообщения о визите.')))),
  ));
  // С предустановкой из журнала окна нужны сразу: дата и мастер уже известны.
  if (state.date) loadSlots();
  else slotBox.replaceChildren(el('small', {}, 'Выберите мастера и дату.'));

  const create = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Создать запись');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  create.onclick = async () => {
    if (!state.masterId || !state.date || !state.start) {
      toast('warn', 'Выберите время', 'Нужны мастер, дата и свободное окно.');
      return;
    }
    if (name.value.trim().length < 2 || phone.value.replace(/\D/g, '').length < 7) {
      toast('warn', 'Проверьте клиента', 'Нужны имя и корректный телефон.');
      return;
    }
    create.disabled = true;
    try {
      const res = await api(url('/api/admin/bookings'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          masterId: state.masterId, serviceId: state.serviceId,
          date: state.date, time: state.start,
          name: name.value.trim(), phone: phone.value.trim(),
          comment: comment.value.trim(), notifyConsent: consent.checked,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { toast('err', 'Запись не создана', body.detail ?? 'Сервер отклонил запрос.'); return; }
      d.close();
      toast('ok', 'Запись создана', `${name.value.trim()} — ${state.date} в ${state.start}`);
      selectPanel('__bookings', { force: true });
    } catch {
      toast('err', 'Запись не создана', 'Сервер недоступен.');
    } finally {
      create.disabled = false;
    }
  };
  d.footer.append(cancel, create);
}

/* ============================== СТАТИСТИКА ============================== */

const CHART_FONT = { family: "'DM Sans', system-ui, sans-serif", size: 12 };
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function destroyCharts() {
  Object.values(charts).forEach((c) => c?.destroy?.());
  charts = {};
}

async function renderStats(panel, days = 30) {
  destroyCharts();
  const head = pageHead('Статистика', 'Что происходит с записями и диалогами за выбранный период.');
  const seg = el('div', { className: 'seg', attrs: { role: 'group', 'aria-label': 'Период' } });
  [[7, 'Неделя'], [30, 'Месяц'], [90, '3 месяца']].forEach(([d, label]) => {
    const b = el('button', { type: 'button', textContent: label, attrs: { 'aria-pressed': String(d === days) } });
    b.onclick = () => renderStats(panel, d);
    seg.append(b);
  });
  head.querySelector('.tools').append(seg);

  const body = el('div', {}, skeletonCards(5));
  panel.replaceChildren(head, body);

  try {
    const res = await apiData(url(`/api/admin/stats?days=${days}`));
    const s = res.stats;
    const tiles = [
      { label: 'Диалогов', value: s.conversations, note: `${s.conversionPct}% дошли до записи`, icon: 'chat', cls: '' },
      { label: 'Записей', value: s.bookings, note: `${s.fromChat} через бота`, icon: 'list', cls: 'accent' },
      { label: 'Успешных', value: s.successful, note: 'активные и состоявшиеся', icon: 'checkCircle', cls: 'ok' },
      { label: 'Отменено', value: s.cancelled, note: `${s.cancelledPct}% от записей`, icon: 'x', cls: 'err' },
      { label: 'Неявок', value: s.noShow, note: `${s.noShowPct}% от записей`, icon: 'warning', cls: 'warn' },
    ];
    const kpis = el('div', { className: 'kpis' }, ...tiles.map((t) => el('div', { className: `kpi ${t.cls}` },
      el('div', { className: 'kpi-top' }, icon(t.icon, { size: 14 }), el('span', { className: 'kpi-label' }, t.label)),
      el('b', {}, String(t.value)), el('small', {}, t.note))));

    const daily = el('canvas', { attrs: { role: 'img', 'aria-label': 'Записи по дням' } });
    const byService = el('canvas', { attrs: { role: 'img', 'aria-label': 'Распределение по услугам' } });
    const byMaster = el('canvas', { attrs: { role: 'img', 'aria-label': 'Распределение по мастерам' } });

    body.replaceChildren(kpis,
      el('div', { className: 'chart-card' },
        el('h3', {}, 'Записи по дням'), el('div', { className: 'chart-box tall' }, daily)),
      el('div', { className: 'charts', style: 'margin-top:16px' },
        el('div', { className: 'chart-card' },
          el('h3', {}, 'Услуги'), el('div', { className: 'chart-box' }, byService)),
        el('div', { className: 'chart-card' },
          el('h3', {}, 'Мастера'), el('div', { className: 'chart-box' }, byMaster))));

    if (!window.Chart) return;
    Chart.defaults.font = CHART_FONT;
    Chart.defaults.color = css('--c-ink-2');

    charts.daily = new Chart(daily, {
      type: 'line',
      data: {
        labels: (res.daily ?? []).map((d) => new Date(d.date).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })),
        datasets: [{
          label: 'Записей', data: (res.daily ?? []).map((d) => d.count),
          borderColor: css('--c-accent'), backgroundColor: 'rgba(217,120,85,.14)',
          fill: true, tension: .35, pointRadius: 3, pointBackgroundColor: css('--c-accent'), borderWidth: 2,
        }],
      },
      options: chartOptions({ y: true }),
    });
    charts.byService = donut(byService, s.byService);
    charts.byMaster = donut(byMaster, s.byMaster);
  } catch (err) {
    body.replaceChildren(errorState('Не удалось загрузить статистику',
      loadFailure(err), () => renderStats(panel, days)));
  }
}

function chartOptions({ y = false } = {}) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { backgroundColor: css('--c-sidebar'), padding: 10, cornerRadius: 8 } },
    scales: y ? {
      x: { grid: { display: false }, border: { display: false } },
      y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: css('--c-line') }, border: { display: false } },
    } : {},
    animation: { duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 400 },
  };
}

const DONUT_COLORS = ['#D97855', '#4F8A68', '#C68A36', '#6E7FA8', '#C95D50', '#E8D8C5', '#A79C91'];

function donut(canvas, rows) {
  if (!rows?.length) {
    canvas.replaceWith(emptyState('chart', 'Нет данных', 'За выбранный период записей не было.'));
    return null;
  }
  return new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: rows.map((r) => r.title ?? r.id),
      datasets: [{
        data: rows.map((r) => r.count),
        backgroundColor: rows.map((_, i) => DONUT_COLORS[i % DONUT_COLORS.length]),
        borderWidth: 2, borderColor: css('--c-surface'),
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '62%',
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, padding: 12, usePointStyle: true } },
        tooltip: { backgroundColor: css('--c-sidebar'), padding: 10, cornerRadius: 8 },
      },
      animation: { duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 400 },
    },
  });
}

/* ============================== РАСПИСАНИЕ ============================== */

/* Расписание — сетка времени, а не список карточек: часы по вертикали, дни по
   горизонтали. Занятость салона так видно глазом, без чтения: где день плотный,
   где дыра в середине, кто из мастеров работает, а кто нет.

   Все три масштаба — одна и та же сетка, отличается только состав колонок:
     день    — колонка на мастера,
     неделя  — колонка на пару «день × мастер»,
     месяц   — колонка на день, мастера внутри неё соседствуют.
   Поэтому и рисуются одним кодом: колонки собирает `lanesOf`, всё остальное
   про них ничего не знает. */

const SCHED = { mode: 'week', date: '', hidden: new Set() };

/* Высота часа и минимальная ширина колонки под масштаб. В месяце колонок
   тридцать, и час в 68 пикселей превращает экран в бесконечную простыню.
   Уже минимальной ширины подпись времени с именем не помещаются, поэтому
   сетка начинает прокручиваться вбок, а не сжимать колонки в ничто.

   Величины живут в скрипте, а не в CSS, потому что здесь же считаются
   пиксельные координаты событий: разъехаться расчёту с вёрсткой негде. */
/* Окно суток, которое показывает сетка, и шаг делений.

   Окно фиксированное, а не «по рабочим часам»: расписание, у которого граница
   ездит вслед за сменами, нельзя сравнивать глазами — вчерашние 14:00 и
   сегодняшние оказываются на разной высоте. Смена, вылезшая за окно, его
   расширяет: рамка не имеет права ничего прятать. */
/* Окно и деления журнала — из настроек салона, а не из числа 9 в коде.
   Салон, который открывается в семь утра, иначе видит первые два часа рабочего
   дня только после того, как в них появится запись. Деления берутся из
   «Деления в журнале»: у одних приём идёт по полчаса, у других — по пять минут,
   и разлиновка должна совпадать с тем, как они думают о времени.

   Шаг делений — не шаг записи: окна клиенту предлагает `slotStepMinutes`. */
const gridDay = () => {
  const hours = data?.salon?.workHours || {};
  const open = minutes(hours.start || '09:00');
  const close = minutes(hours.end || '21:00');
  // Шаг обязан делить час нацело: высота часа кратна числу делений, и при
  // шаге вроде 45 минут деления попадают на доли пикселя, а линии выходят
  // разной толщины. Проверяем это свойством, а не списком значений: список
  // разъедется с `config/schema.json` при первой же новой опции.
  const step = Number(data?.salon?.gridStepMinutes || 15);
  const usable = Number.isInteger(step) && step > 0 && step <= 60 && 60 % step === 0;
  return {
    from: Math.max(0, Math.floor((Number.isFinite(open) ? open : 540) / 60) * 60),
    to: Math.min(1440, Math.ceil((Number.isFinite(close) ? close : 1260) / 60) * 60),
    step: usable ? step : 15,
  };
};

/* Высота часа кратна четырём: шаг сетки — четверть часа, и при нечётной
   высоте деления разъезжаются на доли пикселя, а линии выходят разной
   толщины. */
const SIZES = {
  wide:   { hour: { day: 72, week: 56, month: 48 }, lane: { day: 190, week: 118, month: 104 } },
  narrow: { hour: { day: 56, week: 48, month: 40 }, lane: { day: 136, week: 88, month: 78 } },
};
const sizes = () => (window.matchMedia('(max-width: 760px)').matches ? SIZES.narrow : SIZES.wide);

const RU_MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                   'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const RU_MONTHS_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                       'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const RU_MON_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн',
                      'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const WEEK_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const toKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const fromKey = (key) => new Date(`${key}T12:00:00`);
const shiftKey = (key, days) => {
  const d = fromKey(key);
  d.setDate(d.getDate() + days);
  return toKey(d);
};
/** Понедельник недели, в которую попадает дата. */
const weekStart = (key) => {
  const d = fromKey(key);
  return toKey(new Date(d.setDate(d.getDate() - ((d.getDay() + 6) % 7))));
};
/** Порядковый номер дня недели, где понедельник — 0. */
const weekIndex = (key) => (fromKey(key).getDay() + 6) % 7;

/** «14:30» → 870. «24:00» — конец суток, а не начало: 1440, а не 0. */
const minutes = (hhmm) => {
  const [h, m] = String(hhmm ?? '').split(':').map(Number);
  return Number.isFinite(h) ? h * 60 + (m || 0) : 0;
};
const hhmm = (mins) => `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`;

/* Палитра мастеров: восемь оттенков, дальше повтор. Цвет живёт в CSS
   (`--m0`…`--m7`), здесь только номер — чтобы у мастера был один и тот же
   цвет во всех масштабах и в легенде. */
const MASTER_COLORS = 8;
const colorOf = (masters, id) => {
  const i = masters.findIndex((m) => m.id === id);
  return i < 0 ? 0 : i % MASTER_COLORS;
};

/* ---------- границы периода ---------- */

function periodOf(mode, date) {
  if (mode === 'day') return { from: date, to: date };
  if (mode === 'week') {
    const from = weekStart(date);
    return { from, to: shiftKey(from, 6) };
  }
  const d = fromKey(date);
  const first = new Date(d.getFullYear(), d.getMonth(), 1);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return { from: toKey(first), to: toKey(last) };
}

function periodTitle(mode, date) {
  const d = fromKey(date);
  if (mode === 'month') return `${RU_MONTHS_NOM[d.getMonth()]} ${d.getFullYear()}`;
  if (mode === 'day') return `${WEEK_SHORT[weekIndex(date)]}, ${d.getDate()} ${RU_MONTHS[d.getMonth()]}`;
  const a = fromKey(weekStart(date));
  const b = fromKey(shiftKey(weekStart(date), 6));
  return a.getMonth() === b.getMonth()
    ? `${a.getDate()}–${b.getDate()} ${RU_MONTHS[a.getMonth()]}`
    : `${a.getDate()} ${RU_MON_SHORT[a.getMonth()]} – ${b.getDate()} ${RU_MON_SHORT[b.getMonth()]}`;
}

const shiftPeriod = (mode, date, delta) => {
  if (mode === 'day') return shiftKey(date, delta);
  if (mode === 'week') return shiftKey(date, delta * 7);
  const d = fromKey(date);
  return toKey(new Date(d.getFullYear(), d.getMonth() + delta, 1));
};

/* ---------- экран ---------- */

/* Технический перерыв: обед, уборка, доставка. До этого закрыть час можно было
   только целым выходным в смене — из-за чего обед либо занимали клиентом, либо
   мастер терял день ради часа. */
function newTimeBlock(panel, preset = {}) {
  const masters = data.masters ?? [];
  if (!masters.length) {
    toast('warn', 'Сначала мастера', 'Перерыв ставится конкретному человеку.');
    return;
  }
  const d = drawer({ title: 'Перерыв', subtitle: 'Время закроется и в журнале, и в записи клиента' });
  const master = el('select', {}, ...masters.map((m) =>
    el('option', { value: m.id, textContent: m.name || m.id })));
  master.value = preset.masterId || masters[0].id;
  const date = el('input', { type: 'date', value: preset.date || SCHED.date || toKey(new Date()) });
  const from = el('input', { type: 'time', value: preset.start || '13:00' });
  const to = el('input', { type: 'time', value: preset.end || '14:00' });
  const title = el('input', { type: 'text', value: 'Перерыв', placeholder: 'Обед, уборка, доставка' });

  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field' }, el('label', {}, 'Мастер'), master),
    el('div', { className: 'field' }, el('label', {}, 'Дата'), date),
    el('div', { className: 'field' }, el('label', {}, 'С'), from),
    el('div', { className: 'field' }, el('label', {}, 'До'), to),
    el('div', { className: 'field wide' }, el('label', {}, 'Что это'), title,
      el('small', {}, 'Попадёт в календарь мастера как занятое время — без клиента и услуги.'))));

  const save = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Закрыть время');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  save.onclick = async () => {
    if (from.value >= to.value) {
      toast('warn', 'Проверьте время', 'Конец перерыва должен быть позже начала.');
      return;
    }
    save.disabled = true;
    const res = await api(url('/api/admin/time-blocks'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ masterId: master.value, date: date.value,
                             start: from.value, end: to.value, title: title.value }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      save.disabled = false;
      const detail = payload.detail;
      toast('err', res.status === 409 ? 'На это время есть запись' : 'Не сохранили',
        typeof detail === 'string' ? detail
          : detail?.bookings ? `Записей на это время: ${detail.bookings}` : 'Сервер отклонил запрос.');
      return;
    }
    d.close();
    // Календарь мог не ответить — тогда перерыв есть, а события нет, и молчать
    // об этом нельзя: снаружи время всё ещё выглядит свободным.
    if (payload.warning) toast('warn', 'Перерыв сохранён', payload.warning);
    else toast('ok', 'Время закрыто', `${date.value}, ${from.value}–${to.value}`);
    renderSchedule(panel, date.value);
  };
  d.footer.append(cancel, save);
}

async function removeTimeBlock(block, panel) {
  const ok = await confirmDialog({
    title: `Снять «${block.title}»?`,
    message: `${block.start}–${block.end}. Время вернётся в сетку окон, событие из календаря `
      + 'мастера будет удалено.',
    confirmLabel: 'Снять перерыв',
  });
  if (!ok) return;
  const res = await api(url(`/api/admin/time-blocks/${block.blockId}`), { method: 'DELETE' });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    toast('err', 'Не сняли', typeof payload.detail === 'string' ? payload.detail : 'Сервер отклонил запрос.');
    return;
  }
  if (payload.warning) toast('warn', 'Перерыв снят', payload.warning);
  else toast('ok', 'Перерыв снят', `${block.start}–${block.end}`);
  renderSchedule(panel);
}

function renderSchedule(panel, date = '') {
  if (date) SCHED.date = date;
  if (!SCHED.date) SCHED.date = toKey(new Date());

  const head = pageHead('Расписание', 'Занятость салона: рабочие часы мастеров, записи бота и события из Google Calendar.');
  const seg = el('div', { className: 'seg', attrs: { role: 'group', 'aria-label': 'Масштаб расписания' } });
  [['day', 'День'], ['week', 'Неделя'], ['month', 'Месяц']].forEach(([mode, label]) => {
    const b = el('button', { type: 'button', textContent: label,
      attrs: { 'aria-pressed': String(SCHED.mode === mode) } });
    b.onclick = () => { if (SCHED.mode !== mode) { SCHED.mode = mode; renderSchedule(panel); } };
    seg.append(b);
  });
  const breakBtn = el('button', { className: 'btn btn-secondary btn-sm' },
    icon('clock', { size: 15 }), 'Перерыв');
  breakBtn.onclick = () => newTimeBlock(panel);
  head.querySelector('.tools').append(seg, breakBtn);

  const body = el('div', { className: 'sched' }, skeletonGrid());
  panel.replaceChildren(head, body);
  loadSchedule(panel, body);
}

/** Скелет в форме будущей сетки: подмена содержимого не дёргает вёрстку. */
const skeletonGrid = () => el('div', { className: 'tgrid skeleton' },
  el('div', { className: 'tg-skel' },
    ...Array.from({ length: 8 }, () => el('span', { className: 'skel' }))));

async function loadSchedule(panel, body, { direction = 0 } = {}) {
  const { from, to } = periodOf(SCHED.mode, SCHED.date);
  /* В месяце Google не спрашиваем: тридцать дней чужой занятости в колонке
     шириной сто пикселей всё равно не прочитать, а ждать ответа придётся. */
  const withCalendar = SCHED.mode === 'month' ? '0' : '1';
  try {
    const data = await apiData(url(`/api/admin/schedule/range?from=${from}&to=${to}&calendar=${withCalendar}`));
    drawSchedule(panel, body, data, direction);
  } catch (err) {
    body.replaceChildren(errorState('Не удалось загрузить расписание', loadFailure(err),
      () => { body.replaceChildren(skeletonGrid()); loadSchedule(panel, body); }));
  }
}

/** Перерисовка без скачка: тот же экран, новый период. */
function reload(panel, body, delta) {
  SCHED.date = shiftPeriod(SCHED.mode, SCHED.date, delta);
  loadSchedule(panel, body, { direction: delta });
}

function drawSchedule(panel, body, data, direction) {
  const masters = data.masters ?? [];
  const shown = masters.filter((m) => !SCHED.hidden.has(m.id));

  const nav = periodNav(
    periodTitle(SCHED.mode, SCHED.date),
    (delta) => reload(panel, body, delta),
    () => { SCHED.date = toKey(new Date()); loadSchedule(panel, body); },
    calendarBadge(data.calendarMode, SCHED.mode));

  if (!masters.length) {
    body.replaceChildren(nav, emptyState('users', 'Мастеров нет',
      'Добавьте мастеров в разделе «Мастера» — расписание строится по ним.'));
    return;
  }

  nav.append(masterLegend(masters, () => drawSchedule(panel, body, data, 0)));
  const grid = shown.length
    ? timeGrid(data, shown, panel, body)
    : emptyState('users', 'Все мастера скрыты', 'Включите кого-нибудь в легенде выше.');

  body.replaceChildren(nav, grid);
  animateGrid(grid, direction);
}

/** Стрелки «назад / вперёд / сегодня» — общие для всех трёх масштабов. */
function periodNav(title, onShift, onToday, extra = null) {
  const navBtn = (name, label, onClick) => {
    const b = el('button', { className: 'btn btn-icon', attrs: { 'aria-label': label } }, icon(name, { size: 18 }));
    b.onclick = onClick;
    return b;
  };
  const today = el('button', { className: 'btn btn-secondary btn-sm', textContent: 'Сегодня' });
  today.onclick = onToday;
  return el('div', { className: 'day-nav' },
    navBtn('chevronLeft', 'Предыдущий период', () => onShift(-1)),
    el('span', { className: 'day' }, title),
    navBtn('chevronRight', 'Следующий период', () => onShift(1)),
    today, extra);
}

const calendarBadge = (mode, scale) => {
  if (scale === 'month') {
    return el('span', { className: 'status-badge' }, icon('info', { size: 13 }),
      'месяц строится по записям — занятость Google видна в дне и неделе');
  }
  return mode === 'google'
    ? el('span', { className: 'status-badge ok' }, icon('checkCircle', { size: 13 }), 'Google Calendar подключён')
    : el('span', { className: 'status-badge warn' }, icon('warning', { size: 13 }), 'демо-режим: событий в календаре нет');
};

/** Легенда: она же фильтр. Цвет мастера один и тот же во всех масштабах.

    Должность мастера сюда не идёт — это переключатель, а не карточка: с ролями
    три чипа занимали две строки и оттесняли саму сетку вниз. Роль показывает
    подсказка и колонка в масштабе дня. */
function masterLegend(masters, redraw) {
  const chips = masters.map((m) => {
    const off = SCHED.hidden.has(m.id);
    const chip = el('button', {
      type: 'button', className: `mchip m${colorOf(masters, m.id)}${off ? ' off' : ''}`,
      attrs: {
        'aria-pressed': String(!off),
        title: [m.role, off ? 'скрыт — нажмите, чтобы показать' : 'нажмите, чтобы скрыть']
          .filter(Boolean).join(' · '),
      },
    }, el('span', { className: 'dot', attrs: { 'aria-hidden': 'true' } }),
       el('span', { className: 'nm' }, m.name));
    chip.onclick = () => {
      if (off) SCHED.hidden.delete(m.id); else SCHED.hidden.add(m.id);
      redraw();
      // Отдача на нажатие: фильтр перерисовывает пол-экрана, и без короткого
      // отклика на самом чипе непонятно, что сработало именно от него.
      if (!calm()) {
        const fresh = document.querySelector(`.mchip.m${colorOf(masters, m.id)}`);
        if (fresh) window.Motion.animate(fresh, { scale: [0.94, 1] },
          { type: 'spring', stiffness: 520, damping: 20 });
      }
    };
    return chip;
  });
  return el('div', { className: 'mlegend', attrs: { role: 'group', 'aria-label': 'Мастера' } }, ...chips);
}

/* ---------- колонки ---------- */

/** Состав колонок сетки. Единственное место, где масштабы различаются.

    Колонка на мастера — только в дне. В неделе их вышло бы двадцать одна на
    трёх мастеров, а на экране под сетку меньше тысячи пикселей: колонка в
    сорок пикселей перестаёт быть расписанием и становится полоской цвета.
    Поэтому в неделе и месяце колонка — день, а мастеров внутри различают
    цвет записи и рейка рабочих часов у левого края. */
function lanesOf(data, masters) {
  return data.days.map((day) => {
    const cols = day.columns.filter((c) => masters.some((m) => m.id === c.masterId));
    const lanes = SCHED.mode === 'day'
      ? cols.map((col) => ({ day, cols: [col], merged: false }))
      : [{ day, cols, merged: true }];
    return { day, lanes };
  });
}

/** Вертикальные границы сетки: окно суток, раздвинутое под то, что в него
    не поместилось.

    Начинаем всегда с одного и того же окна — иначе высота одного и того же
    часа скачет от недели к неделе, и сравнивать загрузку глазами нельзя.
    Но ранняя смена и событие Google в семь утра окно расширяют: рамка,
    которая молча прячет занятость, хуже, чем рамка на два часа выше. */
function gridExtent(data, masters) {
  const ids = new Set(masters.map((m) => m.id));
  const day = gridDay();
  let from = day.from;
  let to = day.to;
  data.days.forEach((day) => day.columns.forEach((col) => {
    if (!ids.has(col.masterId)) return;
    if (col.worksToday && col.workHours?.start) {
      from = Math.min(from, minutes(col.workHours.start));
      to = Math.max(to, minutes(col.workHours.end));
    }
    col.events.forEach((e) => {
      from = Math.min(from, minutes(e.start));
      to = Math.max(to, minutes(e.end));
    });
  }));
  from = Math.max(0, Math.floor(from / 60) * 60);
  to = Math.min(1440, Math.ceil(to / 60) * 60);
  return { from, to };
}

/** Раскладка пересекающихся событий: сколько дорожек нужно и кто в какой.

    Классическая задача календаря — две записи в одно время не должны лежать
    друг на друге. Сначала собираем цепочки пересечений, потом внутри цепочки
    кладём каждое событие в первую освободившуюся дорожку. */
function overlapLayout(events) {
  const items = events.map((e, i) => ({
    e, i, from: minutes(e.start), to: Math.max(minutes(e.end), minutes(e.start) + 15),
  })).sort((a, b) => a.from - b.from || b.to - a.to);

  const placed = [];
  let cluster = [];
  let clusterEnd = -1;

  const flush = () => {
    const lanes = [];
    cluster.forEach((it) => {
      let lane = lanes.findIndex((end) => end <= it.from);
      if (lane < 0) { lane = lanes.length; lanes.push(0); }
      lanes[lane] = it.to;
      it.lane = lane;
    });
    cluster.forEach((it) => placed.push({ ...it, lanes: lanes.length }));
    cluster = [];
    clusterEnd = -1;
  };

  items.forEach((it) => {
    if (cluster.length && it.from >= clusterEnd) flush();
    cluster.push(it);
    clusterEnd = Math.max(clusterEnd, it.to);
  });
  if (cluster.length) flush();
  return placed;
}

/* ---------- сама сетка ---------- */

function timeGrid(data, masters, panel, body) {
  const { from, to } = gridExtent(data, masters);
  const size = sizes();
  const step = gridDay().step;
  // Высота часа кратна числу делений: при шаге в пять минут и высоте 56 px
  // деление получается 4⅔ px, линии разъезжаются на доли пикселя и выходят
  // разной толщины. Округляем вверх — сетка становится чуть выше, но ровной.
  const parts = 60 / step;
  const hourPx = Math.ceil(size.hour[SCHED.mode] / parts) * parts;
  const height = ((to - from) / 60) * hourPx;
  const groups = lanesOf(data, masters);
  const lanes = groups.reduce((n, g) => n + g.lanes.length, 0);

  const today = toKey(new Date());
  const inner = el('div', {
    className: `tg-inner ${SCHED.mode}`,
    style: `--lanes:${lanes};--hour:${hourPx}px;--step:${hourPx / parts}px;`
      + `--lane-min:${size.lane[SCHED.mode]}px;--grid-h:${height}px`,
  });

  // Шапка: сверху день, под ним мастер. В месяце нижняя строка — день недели:
  // мастеров там по несколько на колонку, и подписывать их негде.
  inner.append(el('div', { className: 'tg-corner tg-r1' }, el('small', {}, 'время')));
  groups.forEach(({ day, lanes: ls }) => {
    // В дне переходить некуда — мы уже в нём, и кнопка, которая ничего не
    // делает, хуже подписи, которая ничем и не притворяется.
    const zoom = SCHED.mode !== 'day';
    const head = el(zoom ? 'button' : 'div', {
      type: zoom ? 'button' : null,
      className: `tg-gh${zoom ? '' : ' flat'}${day.isToday ? ' today' : ''}${day.date < today ? ' past' : ''}`,
      style: `grid-column: span ${ls.length}`,
      attrs: zoom ? { 'aria-label': `Открыть день ${day.date}` } : {},
    }, ...dayLabel(day));
    if (zoom) head.onclick = () => { SCHED.mode = 'day'; renderSchedule(panel, day.date); };
    inner.append(head);
  });

  inner.append(el('div', { className: 'tg-corner tg-r2' }));
  groups.forEach(({ day, lanes: ls }) => ls.forEach((lane) => {
    inner.append(lane.merged ? crewHead(lane, masters, day) : masterHead(lane, masters, day));
  }));

  // Ось времени и полотно.
  const axis = el('div', { className: 'tg-axis' },
    ...Array.from({ length: (to - from) / 60 + 1 }, (_, i) => el('span', {
      className: 'tg-hr', style: `top:${i * hourPx}px`,
    }, hhmm(from + i * 60))));
  inner.append(axis);

  groups.forEach(({ day, lanes: ls }) => ls.forEach((lane) => {
    inner.append(laneNode(lane, { data, masters, from, to, hourPx, panel, body, day,
      past: day.date < today }));
  }));

  const box = el('div', { className: 'tgrid' }, inner);
  return el('div', { className: 'tgrid-wrap' }, box, ...scrollEdges(box));
}

/** Тени по краям прокрутки.

    Сетка месяца — тридцать одна колонка, из них видно семь. Без края,
    показывающего, что содержимое продолжается, экран выглядит законченным, и
    остальные три недели просто не находят. */
function scrollEdges(box) {
  const edges = ['left', 'right'].map((side) => el('span', {
    className: `tg-edge ${side}`, attrs: { 'aria-hidden': 'true' },
  }));
  const sync = () => {
    const max = box.scrollWidth - box.clientWidth;
    edges[0].classList.toggle('on', box.scrollLeft > 4);
    edges[1].classList.toggle('on', max > 4 && box.scrollLeft < max - 4);
  };
  box.addEventListener('scroll', sync, { passive: true });
  // Первый расчёт — после того, как сетка попала в документ и получила размеры.
  requestAnimationFrame(sync);
  return edges;
}

const dayLabel = (day) => {
  const d = fromKey(day.date);
  const wd = WEEK_SHORT[weekIndex(day.date)];
  if (SCHED.mode === 'month') {
    return [el('b', {}, String(d.getDate())), el('small', {}, wd.toLowerCase())];
  }
  return [
    el('span', { className: 'wd' }, wd),
    el('b', {}, String(d.getDate())),
    el('small', {}, RU_MON_SHORT[d.getMonth()]),
  ];
};

/** Шапка общей колонки: кто из мастеров в этот день выходит.

    Повторять здесь день недели незачем — он строкой выше. А вот «кто сегодня
    в салоне» иначе приходится вычитывать из цветов записей, и в выходной, где
    записей нет, ответа не будет вовсе. */
function crewHead(lane, masters, day) {
  const dots = lane.cols.map((col) => {
    const m = masters.find((x) => x.id === col.masterId) ?? { name: col.masterId };
    return el('span', {
      className: `crew m${colorOf(masters, col.masterId)}${col.worksToday ? '' : ' off'}`,
      attrs: { title: col.worksToday
        ? `${m.name}: ${col.workHours.start}–${col.workHours.end}`
        : `${m.name}: выходной` },
    }, initials(m.name));
  });
  const working = lane.cols.filter((c) => c.worksToday).length;
  return el('div', {
    className: `tg-lh crew-row${day.isToday ? ' today' : ''}${working ? '' : ' off'}`,
    attrs: { 'aria-label': working ? `Работают: ${working}` : 'Выходной' },
  }, ...dots);
}

function masterHead(lane, masters, day) {
  const col = lane.cols[0];
  const m = masters.find((x) => x.id === col.masterId) ?? { name: col.masterId };
  const c = colorOf(masters, col.masterId);
  const compact = SCHED.mode === 'week';
  return el('div', {
    className: `tg-lh m${c}${col.worksToday ? '' : ' off'}${day.isToday ? ' today' : ''}`,
    attrs: { title: `${m.name}${col.worksToday ? ` · ${col.workHours.start}–${col.workHours.end}` : ' · выходной'}` },
  },
    el('span', { className: 'avatar', attrs: { 'aria-hidden': 'true' } }, initials(m.name)),
    compact ? null : el('span', { className: 'nm' }, m.name),
    compact ? null : el('small', {},
      col.worksToday ? `${col.workHours.start}–${col.workHours.end}` : 'выходной'));
}

/** Одна колонка: полосы рабочих часов, события, линия «сейчас». */
function laneNode(lane, ctx) {
  const { masters, from, to, hourPx, panel, body, day, past } = ctx;
  const px = (mins) => ((Math.min(Math.max(mins, from), to) - from) / 60) * hourPx;
  const working = lane.cols.filter((c) => c.worksToday && c.workHours?.start);

  const node = el('div', {
    // Прошедшие дни глушим: в месяце их до тридцати, и без этого взгляд
    // одинаково цепляется за вчера и за послезавтра, хотя поправить можно
    // только второе.
    className: `tg-lane${day.isToday ? ' today' : ''}${past ? ' past' : ''}${working.length ? '' : ' closed'}`,
  });

  // Рабочие часы. В колонке одного мастера — светлая полоса его смены, в общей
  // колонке месяца — тонкие рейки по мастерам: видно, кто когда открыт.
  if (lane.merged) {
    node.append(...unionSpans(working).map(([a, b]) => el('span', {
      className: 'tg-open', style: `top:${px(a)}px;height:${px(b) - px(a)}px`,
    })));
    // Рейка рисуется только тому, чья смена короче общего дня. Пока полосу
    // получал каждый работающий, колонка буднего дня делилась на три цветные
    // трети, из которых две сообщали одно и то же — «работает как весь салон».
    // Разноцветная штриховка под записями читалась как ошибка раскладки, потому
    // что записи ложатся поверх во всю ширину и с этими третями не совпадают.
    //
    // Ширину полосам больше не делим: доля колонки намекала бы, что у мастера
    // своя вертикаль, а её нет. Узкая рейка у левого края отвечает ровно на
    // свой вопрос — «у кого сегодня день короче» — и не спорит с карточками.
    const open = unionSpans(working);
    const dayFrom = open.length ? open[0][0] : 0;
    const dayTo = open.length ? open[open.length - 1][1] : 0;
    const special = working.filter((c) =>
      minutes(c.workHours.start) > dayFrom || minutes(c.workHours.end) < dayTo);
    // Полоса под рейки: иначе карточки, которые ложатся во всю ширину, накроют
    // их в первый же плотный день — а именно в плотный день и важно видеть,
    // у кого смена короче.
    if (special.length) node.style.setProperty('--rails', String(special.length));
    special.forEach((c, i) => {
      const m = masters.find((x) => x.id === c.masterId);
      node.append(el('span', {
        className: `tg-band m${colorOf(masters, c.masterId)}`,
        style: `left:${3 + i * 6}px;`
          + `top:${px(minutes(c.workHours.start))}px;`
          + `height:${px(minutes(c.workHours.end)) - px(minutes(c.workHours.start))}px`,
        attrs: { title: `${m?.name ?? c.masterId}: ${c.workHours.start}–${c.workHours.end}` },
      }));
    });
  } else {
    working.forEach((c) => node.append(el('span', {
      className: `tg-open m${colorOf(masters, c.masterId)} tint`,
      style: `top:${px(minutes(c.workHours.start))}px;height:${px(minutes(c.workHours.end)) - px(minutes(c.workHours.start))}px`,
    })));
  }

  const failed = lane.cols.find((c) => c.error);
  if (failed) node.append(el('span', { className: 'tg-warn', attrs: { title: failed.error } }, icon('warning', { size: 13 })));

  const events = lane.cols.flatMap((c) => c.events.map((e) => ({ ...e, masterId: c.masterId })));
  const layer = el('div', { className: 'tg-evs' });
  overlapLayout(events).forEach(({ e, lane: slot, lanes: n, from: a, to: b }) => {
    layer.append(eventNode(e, {
      top: px(a), height: Math.max(px(b) - px(a), 16), ...spread(slot, n),
      masters, panel, body, date: day.date,
    }));
  });
  node.append(layer);

  const nowAt = nowMinute(ctx);
  if (day.isToday && nowAt !== null) {
    node.append(el('span', { className: 'tg-now', style: `top:${px(nowAt)}px` },
      el('span', { className: 'bead', attrs: { 'aria-hidden': 'true' } })));
  }
  wireEmptyClick(node, { lane, masters, from, to, hourPx, day, past });
  // Колонка носит свои координаты с собой: при отпускании карточки цель ищется
  // по точке на экране, а не по замыканию того обработчика, который начал жест.
  node.__slot = { from, to, hourPx, date: day.date, past, cols: lane.cols };
  return node;
}

/** Клик по свободному месту в колонке открывает форму записи на это время.

    Журнал, в котором кликом ничего не создаётся, — это картинка: администратор
    всё равно идёт в «Записи» и вводит руками то, на что уже показал пальцем.

    Клик отделён от протаскивания порогом: сдвиг больше четырёх пикселей или
    удержание дольше трёхсот миллисекунд — это не клик, а начало жеста, и форму
    открывать нельзя (иначе перетаскивание записи каждый раз будет заканчиваться
    открытой формой). */
function wireEmptyClick(node, { lane, masters, from, to, hourPx, day, past }) {
  if (past) return;   // в прошлое не записывают
  let start = null;

  node.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('.tg-ev')) { start = null; return; }
    start = { x: e.clientX, y: e.clientY, at: Date.now(), offset: e.offsetY };
  });

  node.addEventListener('pointerup', (e) => {
    if (!start || e.target.closest('.tg-ev')) { start = null; return; }
    const moved = Math.hypot(e.clientX - start.x, e.clientY - start.y);
    const held = Date.now() - start.at;
    const offset = start.offset;
    start = null;
    if (moved > 4 || held > 300) return;

    const minute = from + (offset / hourPx) * 60;
    // Шаг сетки и шаг слотов — разные величины: сетка нарисована по четверти
    // часа, а окна у салона могут идти через полчаса. Округляем к сетке, а
    // подбор свободного окна остаётся за формой.
    const step = gridDay().step;
    const snapped = Math.max(from, Math.min(to - step, Math.round(minute / step) * step));

    // В общей колонке месяца мастеров несколько: угадывать за администратора
    // нельзя, поэтому подставляем только день и время.
    const single = lane.cols.length === 1 ? lane.cols[0] : null;
    const master = single ? masters.find((m) => m.id === single.masterId) : null;
    openNewBooking({
      date: day.date, time: hhmm(snapped),
      masterId: single?.masterId, masterName: master?.name,
    });
  });
}

/** Минута «сейчас» по часам салона, если она попадает в сетку.

    Время берём из ответа сервера, а не из часов браузера: салон в Монтевидео,
    владелец может смотреть панель из Москвы, и «сейчас» у него не там. */
function nowMinute({ data, from, to }) {
  const m = minutes(data.now);
  return m >= from && m <= to ? m : null;
}

/** Объединение отрезков: полоса «салон открыт» без стыков и дублей. */
function unionSpans(cols) {
  const spans = cols
    .map((c) => [minutes(c.workHours.start), minutes(c.workHours.end)])
    .sort((a, b) => a[0] - b[0]);
  const out = [];
  spans.forEach(([a, b]) => {
    const last = out[out.length - 1];
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  });
  return out;
}

/** Как разложить пересекающиеся записи по ширине колонки.

    До трёх — поровну. Дальше делить поровну нельзя: в неделе колонка около
    ста пятидесяти пикселей, и треть от неё — сорок, где не помещается ни одно
    имя, только «Кар…». Поэтому от трёх записей карточки идут стопкой: каждая
    почти во всю ширину и сдвинута на край предыдущей. Верхняя читается
    целиком, нижние выглядывают цветным краем — по нему видно, что там кто-то
    ещё, и по нему же можно нажать. */
function spread(slot, lanes) {
  if (lanes <= 2) return { left: (slot / lanes) * 100, width: 100 / lanes, layer: slot };
  const step = 16;                                   // насколько выглядывает нижняя карточка
  return { left: slot * step, width: 100 - step * (lanes - 1), layer: slot };
}

function eventNode(e, { top, height, left, width, layer = 0, masters, panel, body, date }) {
  const booking = e.kind === 'booking';
  const c = colorOf(masters, e.masterId);
  const pending = e.requiresConfirmation && e.status === 'confirmed';
  const cls = ['tg-ev', e.kind, booking ? `m${c}` : '', e.status ?? '', pending ? 'pending' : '',
               height < 34 ? 'tiny' : ''].filter(Boolean).join(' ');
  // Состояние обозначаем значком, а не только цветом полоски: на карточке в
  // цвете мастера зелёная полоска «пришёл» и жёлтая «не пришёл» различаются
  // хуже, чем хотелось бы, а тем, кто цвет различает слабо, — не различаются.
  const mark = pending ? { icon: 'alert', cls: 'warn', label: 'ждёт подтверждения' }
    : e.status === 'completed' ? { icon: 'check', cls: 'ok', label: 'клиент пришёл' }
    : e.status === 'no_show' ? { icon: 'warning', cls: 'warn', label: 'клиент не пришёл' }
    : null;
  const master = masters.find((m) => m.id === e.masterId)?.name ?? '';

  const node = el('button', {
    type: 'button', className: cls,
    style: `top:${top}px;height:${height}px;left:${left}%;`
      + `width:calc(${width}% - 3px);z-index:${layer + 1}`,
    attrs: {
      title: `${e.start}–${e.end} · ${booking ? `${e.client} · ${e.title}` : e.title}${master ? ` · ${master}` : ''}`,
      'aria-label': `${e.start}–${e.end}, ${booking ? e.client : 'занято'}`
        + `${master ? `, ${master}` : ''}${mark ? `, ${mark.label}` : ''}`,
    },
  },
    el('b', {}, e.start),
    el('span', { className: 'ttl' }, booking ? (e.client || e.title)
      : e.kind === 'break' ? (e.title || 'Перерыв') : 'занято'),
    // В дне мастер — это сама колонка, повторять его имя в каждой карточке
    // незачем: там ценнее услуга.
    SCHED.mode === 'day' && booking && height >= 52 ? el('small', {}, e.title) : null,
    mark ? el('span', { className: `pin ${mark.cls}`, attrs: { 'aria-hidden': 'true' } },
      icon(mark.icon, { size: 11 })) : null);

  if (booking) {
    node.onclick = () => openScheduleEvent(e, { master, date, panel, body });
    wireDrag(node, e, { masters, panel, body, date });
  } else if (e.kind === 'break') {
    // Перерыв снимается там же, где стоит: искать его в отдельном списке
    // администратор не будет, а обед у него двигается каждый день.
    node.onclick = () => removeTimeBlock(e, panel);
  } else {
    node.disabled = true;
  }
  return node;
}

/** Перенос записи перетаскиванием.

    Перенос — самый частый ручной сценарий администратора, и в журнале он
    должен делаться жестом, а не открыванием формы. Тяжёлую работу уже делает
    сервер: `PUT /api/admin/bookings/{id}/reschedule` проверяет пересечения,
    двигает событие в календаре мастера и перепланирует уведомления.

    Здесь — только жест и честность про результат: пока сервер не ответил, ничего
    не считается перенесённым, а на отказ карточка возвращается на место. */
function wireDrag(node, e, { masters, panel, body, date }) {
  let drag = null;
  let dragged = false;

  // Клик и жест живут на одной карточке: после перетаскивания браузер всё
  // равно шлёт click, и без этого перехвата каждый перенос заканчивался бы
  // открытой карточкой записи поверх подтверждения.
  node.addEventListener('click', (click) => {
    if (!dragged) return;
    dragged = false;
    click.stopImmediatePropagation();
    click.preventDefault();
  }, true);

  node.addEventListener('pointerdown', (down) => {
    if (down.button !== 0) return;
    drag = { x: down.clientX, y: down.clientY, at: Date.now(), moved: false, id: down.pointerId };
    // Захватываем указатель сразу, а не после первого движения: быстрый жест
    // уводит курсор с карточки первым же событием, и без захвата она перестаёт
    // их получать — перетаскивание просто не начинается.
    try { node.setPointerCapture(down.pointerId); } catch { /* мышь без захвата — переживём */ }
  });

  node.addEventListener('pointermove', (move) => {
    if (!drag) return;
    const dx = move.clientX - drag.x;
    const dy = move.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) <= 4) return;   // это ещё клик, а не жест
    if (!drag.moved) {
      drag.moved = true;
      dragged = true;
      node.classList.add('dragging');
    }
    node.style.transform = `translate(${dx}px, ${dy}px)`;
  });

  const finish = async (up) => {
    if (!drag) return;
    const moved = drag.moved;
    try { node.releasePointerCapture(drag.id); } catch { /* уже отпущен */ }
    drag = null;
    node.classList.remove('dragging');
    node.style.transform = '';
    if (!moved) return;                     // клик обработает onclick
    if (up.type === 'pointercancel') return;

    const target = dropTarget(up.clientX, up.clientY);
    if (!target) { toast('warn', 'Перенос отменён', 'Отпустите карточку внутри сетки.'); return; }
    if (target.date === date && target.masterId === e.masterId && target.time === e.start) return;
    // Занятое время отказываем здесь, а не после запроса: сетка уже знает, что
    // там стоит, и «перенесли?» с последующим «это время занято» — это вопрос,
    // ответ на который был известен заранее.
    const clash = occupied(target, e);
    if (clash) {
      toast('warn', 'Это время занято', `${target.time} — ${clash}. Выберите свободное место в сетке.`);
      renderSchedule(panel);
      return;
    }

    const master = masters.find((m) => m.id === target.masterId)?.name ?? target.masterId;
    const ok = await confirmDialog({
      title: 'Перенести запись?',
      message: `${e.client || e.title}: ${fmtDayLabel(date)}, ${e.start} → `
        + `${fmtDayLabel(target.date)}, ${target.time} · ${master}. `
        + 'Событие в календаре мастера и напоминания клиенту переедут вместе с записью.',
      confirmLabel: 'Перенести',
    });
    if (!ok) return;

    const res = await api(url(`/api/admin/bookings/${e.bookingId}/reschedule`), {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ masterId: target.masterId, date: target.date, time: target.time }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      // Отказ сервера — не «почти получилось»: карточка остаётся там, где была.
      toast('err', res.status === 409 ? 'Это время занято' : 'Не перенесли',
        typeof payload.detail === 'string' ? payload.detail : 'Сервер отклонил перенос.');
      renderSchedule(panel);
      return;
    }
    toast('ok', 'Перенесли', `${fmtDayLabel(target.date)}, ${target.time} · ${master}`);
    renderSchedule(panel, target.date);
  };

  node.addEventListener('pointerup', finish);
  node.addEventListener('pointercancel', finish);
}

/** Что стоит в целевом окне, если оно занято: подпись события или пусто.

    Считаем по той же сетке, которую видит администратор: длительность берём у
    самой переносимой записи, а её собственное место занятым не считаем. */
function occupied(target, moving) {
  const lane = [...document.querySelectorAll('.tg-lane')]
    .find((n) => n.__slot?.date === target.date && n.__slot.cols.length === 1
      && n.__slot.cols[0].masterId === target.masterId);
  if (!lane) return '';
  const span = Math.max(15, minutes(moving.end) - minutes(moving.start));
  const from = minutes(target.time);
  const hit = (lane.__slot.cols[0].events || []).find((ev) => {
    if (ev.bookingId && ev.bookingId === moving.bookingId) return false;
    // «Не пришёл» окно не держит — сервер такую запись занятой не считает,
    // и запрещать поверх неё перенос значило бы врать строже, чем есть.
    if (ev.kind === 'booking' && ev.status && ev.status !== 'confirmed' && ev.status !== 'completed') return false;
    return from < minutes(ev.end) && from + span > minutes(ev.start);
  });
  if (!hit) return '';
  return hit.client || hit.title || (hit.kind === 'break' ? 'перерыв' : 'занято');
}

/** Куда отпустили карточку: колонка мастера, её день и время под курсором. */
function dropTarget(x, y) {
  const under = document.elementFromPoint(x, y);
  const lane = under?.closest('.tg-lane');
  const info = lane?.__slot;
  if (!info || info.past || info.cols.length !== 1) return null;   // общая колонка месяца неоднозначна
  const rect = lane.getBoundingClientRect();
  const minute = info.from + ((y - rect.top) / info.hourPx) * 60;
  const step = gridDay().step;
  const snapped = Math.max(info.from, Math.min(info.to - step, Math.round(minute / step) * step));
  return { date: info.date, masterId: info.cols[0].masterId, time: hhmm(snapped) };
}

/* ---------- карточка события ---------- */

/** Запись из сетки. Данных о ней в расписании меньше, чем в разделе «Записи»,
    поэтому карточку достраиваем оттуда — а действия доступны сразу. */
async function openScheduleEvent(e, { master, date, panel, body }) {
  const d = drawer({
    title: e.client || e.title,
    subtitle: `${fromKey(date).getDate()} ${RU_MONTHS[fromKey(date).getMonth()]} · ${e.start}–${e.end}`,
  });

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Визит'),
      el('dl', { className: 'dl' },
        el('dt', {}, 'Статус'), el('dd', {}, statusBadge({
          status: e.status, requiresConfirmation: e.requiresConfirmation, confirmedByClient: false })),
        el('dt', {}, 'Услуга'), el('dd', {}, e.title),
        el('dt', {}, 'Мастер'), el('dd', {}, master || '—'),
        el('dt', {}, 'Время'), el('dd', {}, `${e.start} – ${e.end}`),
        el('dt', {}, 'Телефон'), el('dd', {},
          e.phone ? el('a', { className: 'phone', href: `tel:${e.phone}` }, e.phone) : '—'))),
  );

  const act = (label, next, cls = 'btn-secondary') => {
    const btn = el('button', { className: `btn ${cls}` }, icon(statusMeta(next).icon, { size: 15 }), label);
    btn.disabled = e.status === next;
    btn.onclick = async () => {
      d.close();
      await scheduleStatus(e, next, { panel, body, date });
    };
    return btn;
  };
  d.footer.append(
    act('Отметить визит', 'completed', 'btn-primary'),
    act('Не пришёл', 'no_show'),
    act('Отменить', 'cancelled', 'btn-ghost'),
  );
}

async function scheduleStatus(e, next, { panel, body, date }) {
  if (next === 'cancelled') {
    const ok = await confirmDialog({
      title: 'Отменить запись?',
      message: `${e.client}, ${fromKey(date).getDate()} ${RU_MONTHS[fromKey(date).getMonth()]} в ${e.start}. `
        + 'Событие удалится из календаря мастера, а будущие напоминания клиенту будут сняты.',
      confirmLabel: 'Отменить запись', cancelLabel: 'Оставить', danger: true,
    });
    if (!ok) return;
  }
  try {
    const res = await apiJson(url(`/api/admin/bookings/${e.bookingId}/status`), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: next }),
    });
    toast('ok', 'Статус обновлён', `${e.client} — ${statusMeta(res.status).label}`);
    loadSchedule(panel, body);
  } catch {
    toast('err', 'Не удалось изменить статус', 'Запись осталась в прежнем состоянии.');
  }
}

/* ---------- движение ---------- */

/* Когда анимировать нельзя — и когда не нужно.

   `document.hidden` здесь не придирка: появление сетки начинается с
   `opacity: 0`, а в скрытой вкладке кадры не идут, и анимация замирает на
   первом. Пользователь возвращается к пустому экрану с невидимыми записями.
   Дешевле не начинать, чем чинить последствия. */
const calm = () => !window.Motion
  || document.hidden
  || window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Появление сетки. Смена периода едет в ту сторону, куда нажали, — стрелка
    «вперёд» и содержимое, приехавшее слева, противоречат друг другу. */
function animateGrid(grid, direction) {
  focusToday(grid);
  if (calm() || !grid.classList.contains('tgrid-wrap')) return;
  const { animate, stagger } = window.Motion;

  /* Сдвиг и масштаб задаём отдельными значениями, а не строкой `transform`.
     Motion разбирает строку покомпонентно, и `'none'` вторым кадром — не
     «вернуться как было», а неразобранный компонент: в части браузеров
     `scale` доезжал до нуля, и записи оставались в разметке, но исчезали с
     экрана. Отдельные `x`, `y`, `scale` собираются библиотекой сами. */
  animate(grid, { opacity: [0, 1], x: [direction * 26, 0] },
    { duration: 0.28, ease: [0.22, 0.9, 0.28, 1] });

  const cells = grid.querySelectorAll('.tg-ev');
  if (cells.length) {
    animate(cells, { opacity: [0, 1], y: [7, 0], scale: [0.97, 1] },
      { duration: 0.34, delay: stagger(0.012, { startDelay: 0.06 }), ease: [0.22, 0.9, 0.28, 1] });
  }
  const bead = grid.querySelector('.tg-now .bead');
  if (bead) animate(bead, { scale: [0, 1] }, { type: 'spring', stiffness: 420, damping: 18, delay: 0.2 });
}

/** Открыть сетку на сегодняшнем дне.

    В месяце тридцать одна колонка и ни один экран их не вмещает. Открывать
    такую сетку на первом числе — значит каждый раз пролистывать её руками
    к сегодняшнему дню, а он и есть то, ради чего расписание открывают. */
function focusToday(wrap) {
  const box = wrap.querySelector?.('.tgrid');
  if (!box) return;

  // Окно суток шире рабочего дня, и в масштабе дня оно в экран не влезает.
  // Открывать сетку на девяти утра, когда салон работает с одиннадцати, —
  // это два пустых часа вместо расписания. Прокручиваем к первой смене,
  // оставив полосу закрытого времени сверху: видно, что сетка там начинается.
  const band = box.querySelector('.tg-open');
  if (band && box.scrollHeight > box.clientHeight) {
    box.scrollTop = Math.max(0, band.offsetTop - 24);
  }

  const today = box.querySelector('.tg-lane.today');
  if (today) {
    const centred = today.offsetLeft + today.offsetWidth / 2 - box.clientWidth / 2;
    box.scrollLeft = Math.max(0, Math.min(centred, box.scrollWidth - box.clientWidth));
  }
  box.dispatchEvent(new Event('scroll'));
}

/* ============================ ГРАФИК МАСТЕРА ============================ */

/* Недельная сетка в карточке мастера отвечает на вопрос «как обычно», этот
   экран — на вопрос «а в этот четверг». Второе меняется куда чаще первого:
   отпуск, подмена, приём до обеда. Без календаря смен мастеру пришлось бы ради
   одного дня переписывать рабочие дни — и потом не забыть вернуть их обратно.

   Два масштаба, как и в расписании: неделя — чтобы разложить ближайшие дни,
   месяц — чтобы увидеть отпуск целиком. Сетка одна и та же, меняется только
   набор дат: два разных календаря пришлось бы чинить дважды. */

const shiftView = { masterId: '', mode: 'month', date: '', dir: 0 };

const SHIFT_LEGEND = [
  ['week', 'по недельной сетке'],
  ['custom', 'своя смена'],
  ['off', 'выходной'],
];

function renderShifts(panel) {
  const list = data?.masters ?? [];
  if (!list.length) {
    panel.replaceChildren(pageHead('График мастеров', ''),
      emptyState('users', 'Мастеров нет', 'Добавьте мастеров в разделе «Мастера».'));
    return;
  }
  if (!list.some((m) => m.id === shiftView.masterId)) shiftView.masterId = list[0].id;
  if (!shiftView.date) shiftView.date = toKey(new Date());

  const head = pageHead('График мастеров', 'Отпуска, подмены и особые часы');
  const masterSeg = el('div', { className: 'seg', attrs: { role: 'group', 'aria-label': 'Мастер' } });
  list.forEach((m) => {
    const b = el('button', { type: 'button', textContent: m.name || m.id,
      attrs: { 'aria-pressed': String(m.id === shiftView.masterId) } });
    b.onclick = () => { shiftView.masterId = m.id; shiftView.dir = 0; renderShifts(panel); };
    masterSeg.append(b);
  });
  const modeSeg = el('div', { className: 'seg', attrs: { role: 'group', 'aria-label': 'Масштаб графика' } });
  [['week', 'Неделя'], ['month', 'Месяц']].forEach(([mode, label]) => {
    const b = el('button', { type: 'button', textContent: label,
      attrs: { 'aria-pressed': String(shiftView.mode === mode) } });
    b.onclick = () => { shiftView.mode = mode; shiftView.dir = 0; renderShifts(panel); };
    modeSeg.append(b);
  });
  head.querySelector('.tools').append(masterSeg, modeSeg);

  const body = el('div', {}, skeletonTable(shiftView.mode === 'week' ? 1 : 5, 7));
  panel.replaceChildren(head, body);
  drawShifts(panel, body);
}

/** Даты, попадающие в сетку: неделя — семь дней, месяц — полные недели вокруг него. */
function shiftDates() {
  if (shiftView.mode === 'week') {
    const start = weekStart(shiftView.date);
    return Array.from({ length: 7 }, (_, i) => shiftKey(start, i));
  }
  const cursor = fromKey(shiftView.date);
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const gridStart = new Date(first);
  gridStart.setDate(1 - ((first.getDay() + 6) % 7));
  const all = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(gridStart);
    d.setDate(gridStart.getDate() + i);
    return toKey(d);
  });
  // Шестая строка нужна не каждый месяц — пустую не рисуем.
  const rows = all.slice(35).some((k) => fromKey(k).getMonth() === cursor.getMonth()) ? 6 : 5;
  return all.slice(0, rows * 7);
}

async function drawShifts(panel, body) {
  const dates = shiftDates();
  // Неделя на стыке месяцев живёт в двух ответах — запрашиваем оба и склеиваем.
  // В сетке месяца хвосты соседних месяцев нарисованы пустыми, и данные по ним
  // не нужны: три запроса вместо одного ради серых чисел по краям.
  const months = shiftView.mode === 'week'
    ? [...new Set(dates.map((d) => d.slice(0, 7)))]
    : [shiftView.date.slice(0, 7)];
  let packs;
  try {
    packs = await Promise.all(months.map((m) => apiData(
      url(`/api/admin/masters/${encodeURIComponent(shiftView.masterId)}/shifts?month=${m}`))));
  } catch (err) {
    body.replaceChildren(errorState('Не удалось загрузить график', loadFailure(err),
      () => drawShifts(panel, body)));
    return;
  }
  const res = packs[0];
  const byDate = new Map(packs.flatMap((p) => p.days).map((d) => [d.date, d]));

  const step = (delta) => {
    shiftView.dir = delta;
    shiftView.date = shiftView.mode === 'week'
      ? shiftKey(weekStart(shiftView.date), delta * 7)
      : toKey(new Date(fromKey(shiftView.date).getFullYear(),
                       fromKey(shiftView.date).getMonth() + delta, 1));
    renderShifts(panel);
  };
  const nav = periodNav(
    shiftTitle(dates),
    step,
    () => { shiftView.dir = 0; shiftView.date = toKey(new Date()); renderShifts(panel); },
    el('span', { className: 'status-badge' }, icon('clock', { size: 13 }), weekGridLabel(res)));

  const month = fromKey(shiftView.date).getMonth();
  const slide = shiftView.dir > 0 ? ' from-right' : (shiftView.dir < 0 ? ' from-left' : '');
  // Неделя — таблица часов, месяц — сетка дней. В неделе дней всего семь, и
  // место есть на то, чтобы показать саму смену, а не подпись «11:00–20:00»:
  // отпуск и приём до обеда видно формой закрашенного столбца.
  const grid = shiftView.mode === 'week'
    ? shiftWeekTable(panel, res, byDate, dates, slide)
    : el('div', { className: `month-grid shift-grid month${slide}` },
        ...WEEK_SHORT.map((w) => el('div', { className: 'mhead' }, w)),
        ...dates.map((key, i) => {
          const cell = shiftCell(panel, res, byDate.get(key), key, month);
          cell.style.setProperty('--i', String(i));
          return cell;
        }));
  // Вспышку ставит сама ячейка при сборке: ждать, пока сетка окажется в DOM,
  // и искать её потом селектором — значит проиграть гонку с соседним рендером.
  shiftView.dir = 0;
  shiftView.changed = '';

  const legend = el('div', { className: 'legend' },
    ...SHIFT_LEGEND.map(([kind, label]) => el('span', { className: 'legend-item' },
      el('i', { className: `swatch ${kind}`, attrs: { 'aria-hidden': 'true' } }), label)));

  body.replaceChildren(nav, grid, legend,
    el('p', { className: 'hint', style: 'margin-top:10px' },
      'Клик по дню меняет график только у выбранного мастера и только на эту дату. '
      + 'Постоянный график — в разделе «Мастера».'));
}

/** Неделя как таблица: строка — четверть часа, столбец — день.

    Отпуска и подмены задаются часами, а карточка дня показывала только их
    подпись: чтобы понять, кто в среду выходит позже, приходилось читать семь
    строк «11:00–20:00» и сравнивать в уме. В таблице смена — закрашенный
    отрезок столбца, и лишний час утром виден, не доходя до цифр.

    Окно и шаг общие с расписанием (`gridDay()`): два экрана про одни и те же
    сутки обязаны мерить их одинаково. */
function shiftWeekTable(panel, res, byDate, dates, slide) {
  const { from, to, step } = gridDay();
  const rows = Math.ceil((to - from) / step);
  const today = toKey(new Date());

  const inner = el('div', { className: 'sg-inner', style: `--rows:${rows}` });
  inner.append(el('div', { className: 'sg-corner' }, el('small', {}, 'время')));
  dates.forEach((key) => inner.append(shiftDayHead(panel, res, byDate.get(key), key, today)));

  for (let r = 0; r < rows; r += 1) {
    const min = from + r * step;
    const hour = min % 60 === 0;
    inner.append(el('div', { className: `sg-time${hour ? ' hour' : ''}` }, hour ? hhmm(min) : ''));
    dates.forEach((key) => inner.append(shiftSlot(panel, res, byDate.get(key), key, min, today)));
  }
  return el('div', { className: `sg-wrap${slide}` }, inner);
}

/** Шапка столбца: число, день недели и часы смены одной строкой. */
function shiftDayHead(panel, res, day, key, today) {
  const d = fromKey(key);
  const kind = !day ? '' : (day.source === 'week' ? (day.works ? 'week' : 'weekoff') : day.source);
  const head = el(day && !day.past ? 'button' : 'div', {
    type: day && !day.past ? 'button' : null,
    className: `sg-head ${kind}${key === today ? ' today' : ''}${day?.past ? ' past' : ''}`,
    attrs: day && !day.past
      ? { 'aria-label': `Изменить график на ${key}` }
      : {},
  },
    el('span', { className: 'wd' }, WEEK_SHORT[weekIndex(key)]),
    el('b', {}, String(d.getDate())),
    el('small', {}, day ? (day.works ? `${day.start}–${day.end}` : 'выходной') : '—'),
    day?.bookings
      ? el('span', { className: 'sg-count', attrs: { title: `записей: ${day.bookings}` } },
          icon('list', { size: 10 }), String(day.bookings))
      : null,
    day && day.source !== 'week'
      ? el('i', { className: 'shift-mark', attrs: { 'aria-hidden': 'true' } })
      : null);
  if (day && !day.past) head.onclick = () => editShift(panel, res, day);
  return head;
}

/** Одна клетка таблицы: попадает ли эта четверть часа в смену мастера. */
function shiftSlot(panel, res, day, key, min, today) {
  const on = !!day?.works && min >= minutes(day.start) && min < minutes(day.end);
  const kind = !day ? '' : (day.source === 'week' ? 'week' : day.source);
  const hour = min % 60 === 0;
  const cell = el('div', {
    className: `sg-cell${on ? ` on ${kind}` : ''}${hour ? ' hour' : ''}`
      + `${key === today ? ' today' : ''}${day?.past ? ' past' : ''}`,
  });
  // Клик по любой клетке столбца открывает тот же день: попасть в узкую
  // шапку мышью труднее, чем в столбец, а меняется всё равно весь день.
  if (day && !day.past) {
    cell.onclick = () => editShift(panel, res, day);
    cell.title = `${hhmm(min)} · ${day.works ? `${day.start}–${day.end}` : 'выходной'}`;
  }
  return cell;
}

/** Подпись между стрелками: «17–23 августа» для недели, «Август 2026» для месяца. */
function shiftTitle(dates) {
  if (shiftView.mode !== 'week') {
    const d = fromKey(shiftView.date);
    return `${RU_MONTHS_NOM[d.getMonth()]} ${d.getFullYear()}`;
  }
  const a = fromKey(dates[0]);
  const b = fromKey(dates[6]);
  return a.getMonth() === b.getMonth()
    ? `${a.getDate()}–${b.getDate()} ${RU_MONTHS[a.getMonth()]}`
    : `${a.getDate()} ${RU_MONTHS[a.getMonth()]} – ${b.getDate()} ${RU_MONTHS[b.getMonth()]}`;
}

/** Чем живёт день, которого не касались. */
function weekGridLabel(res) {
  const days = res.workDays.length
    ? WEEK_SHORT.filter((_, i) => res.workDays.includes((i + 1) % 7)).join(' ')
    : 'дни не заданы';
  const hours = res.weekHours.start || res.weekHours.end
    ? `${res.weekHours.start || res.salonHours.start}–${res.weekHours.end || res.salonHours.end}`
    : `${res.salonHours.start ?? ''}–${res.salonHours.end ?? ''} как салон`;
  return `обычно: ${days} · ${hours}`;
}

function shiftCell(panel, res, day, key, month) {
  const inGrid = shiftView.mode === 'week' || fromKey(key).getMonth() === month;
  if (!day || !inGrid) {
    return el('div', { className: 'mcell out' },
      el('span', { className: 'mdate' }, String(fromKey(key).getDate())));
  }
  const kind = day.source === 'week' ? (day.works ? 'week' : 'weekoff') : day.source;
  // День, который только что правили, коротко подсвечивается: панель закрылась,
  // а понять, куда именно легло изменение, нужно без поиска глазами.
  const cell = el('div', {
    className: `mcell shift ${kind}${day.date === res.today ? ' today' : ''}`
      + `${day.past ? ' past' : ''}${day.date === shiftView.changed ? ' changed' : ''}`,
    tabIndex: day.past ? -1 : 0,
    dataset: { date: day.date },
    attrs: {
      role: 'button',
      'aria-label': `${day.date}: ${day.works ? `работает ${day.start}–${day.end}` : 'выходной'}`
        + (day.bookings ? `, записей ${day.bookings}` : ''),
    },
  },
    el('span', { className: 'mdate' }, String(fromKey(key).getDate())),
    el('span', { className: 'shift-hours' }, day.works ? `${day.start}–${day.end}` : 'выходной'),
    day.bookings
      ? el('span', { className: 'shift-count' }, icon('list', { size: 11 }),
          shiftView.mode === 'week' ? `записей: ${day.bookings}` : String(day.bookings))
      : null,
    day.source !== 'week' ? el('i', { className: 'shift-mark', attrs: { 'aria-hidden': 'true' } }) : null);

  if (day.past) return cell;
  const open = () => editShift(panel, res, day);
  cell.onclick = open;
  cell.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
  return cell;
}

/** Один день: как обычно, выходной или своя смена. */
function editShift(panel, res, day) {
  const human = fromKey(day.date).toLocaleDateString('ru-RU',
    { day: 'numeric', month: 'long', weekday: 'long' });
  const d = drawer({ title: res.master, subtitle: human });

  const start = el('input', { type: 'time', value: day.source === 'custom' ? day.start : (res.salonHours.start ?? '') });
  const end = el('input', { type: 'time', value: day.source === 'custom' ? day.end : (res.salonHours.end ?? '') });
  const hours = el('div', { className: 'reveal' },
    el('div', {}, el('div', { className: 'grid' },
      el('div', { className: 'field' }, el('label', {}, 'Начало смены'), start),
      el('div', { className: 'field' }, el('label', {}, 'Конец смены'), end))));

  const modes = [
    ['default', 'Как обычно', 'День живёт по недельной сетке мастера.'],
    ['work', 'Своя смена', 'Работает в этот день, но в другие часы.'],
    ['off', 'Выходной', 'Свободных окон в этот день клиент не увидит.'],
  ];
  let mode = day.source === 'off' ? 'off' : (day.source === 'custom' ? 'work' : 'default');

  const options = el('div', { className: 'choice-list' });
  const paint = () => {
    [...options.children].forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    hours.classList.toggle('open', mode === 'work');
  };
  modes.forEach(([value, label, hint]) => {
    const b = el('button', { type: 'button', className: 'choice', dataset: { mode: value } },
      el('b', {}, label), el('small', {}, hint));
    b.onclick = () => { mode = value; paint(); };
    options.append(b);
  });

  d.body.append(options, hours);
  if (day.bookings) {
    d.body.append(el('p', { className: 'hint', style: 'margin-top:12px' },
      `На этот день уже есть записи: ${day.bookings}. Выходной их не отменяет — `
      + 'перенесите или отмените их в разделе «Записи».'));
  }
  paint();

  const save = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Сохранить');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  save.onclick = async () => {
    save.disabled = true;
    const payload = { date: day.date, mode };
    if (mode === 'work') { payload.start = start.value; payload.end = end.value; }
    const done = await putShift(payload, { force: false });
    save.disabled = false;
    if (!done) return;
    d.close();
    shiftView.changed = day.date;
    renderShifts(panel);
  };
  d.footer.append(cancel, save);
}

/** Отправка одного дня. Выходной поверх записей сначала переспрашивает. */
async function putShift(payload, { force }) {
  const res = await api(url(`/api/admin/masters/${encodeURIComponent(shiftView.masterId)}/shifts`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, force }),
  });
  if (res.ok) {
    toast('ok', 'График обновлён', payload.date);
    return true;
  }
  const body = await res.json().catch(() => ({}));
  const detail = body.detail;
  if (res.status === 409 && detail?.bookings) {
    const yes = await confirmDialog({
      title: 'В этот день есть записи',
      message: `Записей: ${detail.bookings}. Выходной их не отменит — клиенты останутся в расписании.`,
      confirmLabel: 'Всё равно закрыть день',
      danger: true,
    });
    if (!yes) return false;
    return putShift(payload, { force: true });
  }
  toast('err', 'Не сохранилось', typeof detail === 'string' ? detail : 'Сервер отклонил запрос.');
  return false;
}

/* ============================== ДИАЛОГИ ================================= */

async function renderConversations(panel) {
  const head = pageHead('Диалоги', 'Переписка клиентов с ботом и записи, к которым она привела.');
  const body = el('div', {}, skeletonTable(6, 2));
  panel.replaceChildren(head, body);

  try {
    const { conversations } = await apiData(url('/api/admin/conversations?limit=100'));
    if (!conversations.length) {
      body.replaceChildren(el('div', { className: 'card' },
        emptyState('chat', 'Диалогов пока нет',
          'Как только клиент напишет боту или откроет виджет, разговор появится здесь.')));
      return;
    }
    const list = el('div', { className: 'dialogs' });
    const pane = el('div', { className: 'dialog-pane' },
      emptyState('chat', 'Выберите диалог', 'Слева — список разговоров с ботом.'));

    conversations.forEach((c) => {
      const when = new Date(c.startedAt).toLocaleString('ru-RU',
        { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
      const item = el('button', { type: 'button', className: 'dialog-item', attrs: { 'aria-current': 'false' } },
        el('div', { className: 'dialog-top' },
          el('b', {}, when),
          c.bookings
            ? el('span', { className: 'badge completed' }, icon('checkCircle', { size: 12 }), `запись ${c.bookings}`)
            : el('span', { className: 'badge' }, 'без записи')),
        // При выключенном AI клиент записывается кнопками, и переписки не
        // возникает вовсе. «0 сообщений» и прочерк выглядели как поломка —
        // хотя произошло ровно то, что задумано.
        el('span', { className: 'dialog-first' },
          c.firstMessage || (c.bookings ? 'Запись через виджет — клиент выбирал кнопками' : '—')),
        el('small', {}, c.messages
          ? `${c.messages} ${pluralMessages(c.messages)} · ${c.channel}`
          : `без переписки · ${c.channel}`));
      item.onclick = async () => {
        list.querySelectorAll('.dialog-item').forEach((x) => x.setAttribute('aria-current', 'false'));
        item.setAttribute('aria-current', 'true');
        pane.replaceChildren(el('div', { style: 'display:grid;gap:10px' },
          ...Array.from({ length: 4 }, () => el('span', { className: 'skel skel-line', style: 'height:34px' }))));
        try {
          const detail = await apiData(url(`/api/admin/conversations/${c.id}`));
          // Без переписки показывать пустую ленту бессмысленно: владелец решает,
          // что диалог не открылся. Вместо неё — что именно клиент заказал.
          const head = detail.messages.length
            ? el('div', { className: 'thread' }, ...detail.messages.map((m) => el('div',
                { className: `bubble ${m.role}` },
                el('span', {}, m.content),
                el('small', {}, new Date(m.at).toLocaleTimeString('ru-RU',
                  { hour: '2-digit', minute: '2-digit' })))))
            : el('div', { className: 'card', style: 'box-shadow:none' },
                emptyState('chat', 'Переписки нет',
                  detail.bookings.length
                    ? 'Клиент записался кнопками в виджете — свободный диалог включается в разделе «AI-диалог».'
                    : 'Клиент открыл виджет, но ничего не написал и не записался.'));

          pane.replaceChildren(head,
            ...(detail.bookings.length ? [dialogBookings(detail.bookings)] : []));
        } catch (err) {
          pane.replaceChildren(errorState('Не удалось открыть диалог', loadFailure(err)));
        }
      };
      list.append(item);
    });

    body.replaceChildren(el('div', { className: 'dialogs-wrap' }, list, pane));
  } catch (err) {
    body.replaceChildren(errorState('Не удалось загрузить диалоги',
      loadFailure(err), () => renderConversations(panel)));
  }
}

const pluralMessages = (n) => (n % 10 === 1 && n % 100 !== 11 ? 'сообщение'
  : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'сообщения' : 'сообщений');

/** Записи диалога подробно.

    Владелец открывает диалог, чтобы понять, чем он кончился, — и дальше ему
    нужен телефон клиента, комментарий и судьба напоминаний. Раньше карточка
    показывала пять полей, а за остальным приходилось идти в раздел «Записи»
    и искать там ту же запись руками. Показываем всё, что о ней известно. */
function dialogBookings(bookings) {
  return el('div', { className: 'card', style: 'box-shadow:none;margin-top:12px' },
    el('h3', { className: 'section-title' }, bookings.length > 1 ? 'Записи' : 'Запись'),
    ...bookings.map(bookingFacts));
}

const SOURCE_LABEL = { web: 'веб-виджет на сайте', whatsapp: 'WhatsApp',
                       telegram: 'Telegram', admin: 'создана в панели' };

const NOTIFY_TYPE = {
  booking_confirmation: 'подтверждение клиенту',
  booking_reminder_day_before: 'напоминание накануне',
  booking_reminder_today: 'напоминание в день визита',
  booking_cancelled: 'отмена — клиенту',
  master_booking_cancelled: 'отмена — мастеру',
  booking_rescheduled: 'перенос — клиенту',
  owner_new_booking: 'новая запись — владельцу',
  master_new_booking: 'новая запись — мастеру',
  owner_booking_rescheduled: 'перенос — владельцу',
  master_booking_rescheduled: 'перенос — мастеру',
  owner_delivery_failed: 'сообщение не дошло — владельцу',
};

const NOTIFY_STATUS = {
  scheduled: { label: 'запланировано', cls: 'pending' },
  sending: { label: 'отправляется', cls: 'pending' },
  sent: { label: 'отправлено', cls: 'confirmed' },
  delivered: { label: 'доставлено', cls: 'completed' },
  failed: { label: 'не доставлено', cls: 'no_show' },
  cancelled: { label: 'снято', cls: 'cancelled' },
};

/** Длительность считаем по самой записи: услуга могла с тех пор измениться. */
function bookingLength(b) {
  const mins = Math.round((new Date(b.end) - new Date(b.start)) / 60000);
  if (!Number.isFinite(mins) || mins <= 0) return b.duration ? `${b.duration} мин` : '—';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h ? `${h} ч${m ? ` ${m} мин` : ''}` : `${m} мин`;
}

function bookingFacts(b) {
  const row = (dt, dd) => [el('dt', {}, dt), el('dd', {}, dd)];
  const when = new Date(b.start).toLocaleDateString('ru-RU',
    { day: '2-digit', month: 'long', weekday: 'long' });

  const visit = el('dl', { className: 'dl' },
    ...row('Статус', statusBadge(b)),
    ...row('Когда', `${when}, ${fmtTime(b.start)} – ${fmtTime(b.end)}`),
    ...row('Длительность', bookingLength(b)),
    ...row('Услуга', b.service),
    ...(b.price ? row('Цена', b.price) : []),
    ...row('Мастер', b.masterRole ? `${b.master} · ${b.masterRole}` : b.master),
    ...(b.requiresConfirmation
      ? row('Подтверждение', b.confirmedByClient
          ? 'клиент подтвердил визит'
          : 'запись требует подтверждения — клиент ещё не ответил')
      : []));

  const client = el('dl', { className: 'dl' },
    ...row('Имя', b.client || '—'),
    ...row('Телефон', b.phone
      ? el('a', { className: 'phone', href: `tel:${b.phone}` }, b.phone)
      : 'не указан'),
    ...row('Уведомления', b.notifyConsent ? 'согласие получено' : 'клиент отказался'),
    ...row('Комментарий', b.comment || 'нет'));

  const origin = el('dl', { className: 'dl' },
    ...row('Источник', SOURCE_LABEL[b.channel] ?? 'неизвестен'),
    ...row('Создана', `${fmtDate(b.createdAt)}, ${fmtTime(b.createdAt)}`),
    ...row('Календарь', b.eventId
      ? el('span', { className: 'badge completed' }, icon('checkCircle', { size: 12 }), 'событие создано')
      : el('span', { className: 'badge no_show' }, icon('warning', { size: 12 }), 'события нет')),
    ...(b.htmlLink
      ? row('Событие', el('a', { href: b.htmlLink, target: '_blank', rel: 'noopener', className: 'phone' },
          'Открыть в Google Calendar'))
      : []),
    ...row('Номер записи', el('code', {}, b.id)));

  const part = (title, dl) => el('div', { className: 'facts-part' },
    el('h4', { className: 'section-title' }, title), dl);
  return el('div', { className: 'booking-facts' },
    part('Визит', visit), part('Клиент', client), part('Происхождение', origin),
    notifyLog(b.notifications ?? []));
}

/** Что ушло клиенту и своим — иначе «клиент не пришёл» невозможно отличить от
    «напоминание не дошло». */
function notifyLog(list) {
  const box = el('div', { className: 'facts-part' },
    el('h4', { className: 'section-title' }, 'Уведомления'));
  if (!list.length) {
    box.append(el('p', { className: 'hint' },
      'Ни одного уведомления по этой записи не ставилось — отправка выключена или клиент отказался.'));
    return box;
  }
  const rows = [...list].sort((a, b) => (a.scheduled_at || '').localeCompare(b.scheduled_at || ''));
  box.append(el('div', { className: 'notify-log' }, ...rows.map((n) => {
    const meta = NOTIFY_STATUS[n.status] ?? { label: n.status, cls: '' };
    const at = n.delivered_at || n.sent_at || n.scheduled_at;
    return el('div', { className: 'notify-row' },
      el('span', { className: `badge ${meta.cls}` }, meta.label),
      el('span', {}, NOTIFY_TYPE[n.type] ?? n.type),
      el('small', {}, `${n.channel}${n.recipient ? ` → ${n.recipient}` : ''}`
        + (at ? ` · ${fmtDate(at)}, ${fmtTime(at)}` : '')
        + (n.error ? ` · ${n.error}` : '')));
  })));
  return box;
}

/* ======================== ОЧЕРЕДЬ УВЕДОМЛЕНИЙ ========================= */

const notificationState = { all: [], status: '', audience: '' };

async function renderNotificationQueue(panel) {
  const head = pageHead('Очередь уведомлений',
    'Подтверждения, напоминания и сообщения своим — включая ошибки доставки.');
  const refresh = el('button', { className: 'btn btn-secondary' }, icon('refresh', { size: 15 }), 'Обновить');
  refresh.onclick = () => renderNotificationQueue(panel);
  head.querySelector('.tools').append(refresh);
  const body = el('div', {}, skeletonCards(4), skeletonTable());
  panel.replaceChildren(head, body);

  try {
    const res = await apiData(url(`/api/notifications?tenant=${encodeURIComponent(tenant)}&limit=300`));
    notificationState.all = res.notifications ?? [];
    drawNotificationQueue(body);
  } catch (err) {
    body.replaceChildren(errorState('Не удалось загрузить очередь',
      loadFailure(err), () => renderNotificationQueue(panel)));
  }
}

function drawNotificationQueue(body) {
  const s = notificationState;
  const counts = (status) => s.all.filter((n) => n.status === status).length;
  const kpis = el('div', { className: 'kpis' }, ...[
    { label: 'Ожидают', value: counts('scheduled') + counts('sending'), note: 'в очереди', icon: 'clock', cls: 'accent' },
    { label: 'Доставлено', value: counts('delivered'), note: 'подтверждено провайдером', icon: 'checkCircle', cls: 'ok' },
    { label: 'Отправлено', value: counts('sent'), note: 'принято провайдером', icon: 'send', cls: '' },
    { label: 'Ошибки', value: counts('failed'), note: 'нужно проверить', icon: 'warning', cls: 'err' },
  ].map((t) => el('div', { className: `kpi ${t.cls}` },
    el('div', { className: 'kpi-top' }, icon(t.icon, { size: 14 }), el('span', { className: 'kpi-label' }, t.label)),
    el('b', {}, String(t.value)), el('small', {}, t.note))));

  const pick = (label, value, options, onPick) => {
    const select = el('select', { attrs: { 'aria-label': label } },
      el('option', { value: '', textContent: label }),
      ...options.map((o) => el('option', { value: o.value, textContent: o.label, selected: o.value === value })));
    select.onchange = () => { onPick(select.value); drawNotificationQueue(body); };
    return select;
  };
  const reset = el('button', { className: 'btn btn-ghost btn-sm' }, icon('filterOff', { size: 15 }), 'Сбросить');
  reset.disabled = !s.status && !s.audience;
  reset.onclick = () => { Object.assign(s, { status: '', audience: '' }); drawNotificationQueue(body); };
  const filters = el('div', { className: 'filters' },
    pick('Любой статус', s.status,
      Object.entries(NOTIFY_STATUS).map(([value, meta]) => ({ value, label: meta.label })),
      (value) => { s.status = value; }),
    pick('Любой получатель', s.audience, [
      { value: 'client', label: 'Клиент' }, { value: 'owner', label: 'Владелец' },
      { value: 'staff', label: 'Команда' }, { value: 'master', label: 'Мастер' },
    ], (value) => { s.audience = value; }),
    el('span', { className: 'spacer' }), reset);

  const rows = s.all.filter((n) => (!s.status || n.status === s.status)
    && (!s.audience || n.audience === s.audience));
  body.replaceChildren(kpis, filters, notificationTable(rows));
}

function notificationTable(rows) {
  if (!notificationState.all.length) {
    return el('div', { className: 'table-wrap' }, emptyState('bell', 'Очередь пока пуста',
      'После первой записи здесь появятся подтверждения и напоминания.'));
  }
  if (!rows.length) {
    return el('div', { className: 'table-wrap' }, emptyState('search', 'Ничего не найдено',
      'Под выбранные фильтры не подходит ни одного уведомления.'));
  }

  const audience = { client: 'клиент', owner: 'владелец', staff: 'команда', master: 'мастер' };
  const tbody = el('tbody', {}, ...rows.map((n) => {
    const meta = NOTIFY_STATUS[n.status] ?? { label: n.status, cls: '' };
    const at = n.delivered_at || n.sent_at || n.scheduled_at;
    return el('tr', {},
      el('td', { className: 'cell-when' }, el('b', {}, at ? fmtTime(at) : '—'),
        el('small', {}, at ? fmtDate(at) : 'без даты')),
      el('td', {}, NOTIFY_TYPE[n.type] ?? n.type),
      el('td', {}, audience[n.audience] ?? n.audience),
      el('td', {}, `${n.channel} · ${n.provider}`),
      el('td', {}, n.recipient || '—'),
      el('td', {}, el('span', { className: `badge ${meta.cls}` }, meta.label)),
      el('td', {}, n.error
        ? el('span', { className: 'notify-error', title: n.error }, n.error)
        : el('span', { className: 'hint' }, n.attempts ? `попыток: ${n.attempts}` : '—')));
  }));
  return el('div', { className: 'table-wrap' },
    el('div', { className: 'table-scroll' },
      el('table', { className: 'data' },
        el('thead', {}, el('tr', {}, ...['Когда', 'Сообщение', 'Кому', 'Канал', 'Получатель', 'Статус', 'Ошибка']
          .map((label) => el('th', { attrs: { scope: 'col' } }, label)))), tbody)),
    el('div', { className: 'table-foot' },
      el('span', { className: 'count' }, `Показано ${rows.length} из ${notificationState.all.length}`)));
}

/* ============================== ТАРИФ ================================== */

async function renderBilling(panel) {
  const head = pageHead('Тариф', 'Подписка и потребление лимитов в текущем месяце.');
  const body = el('div', {}, skeletonCards(3));
  panel.replaceChildren(head, body);

  try {
    const res = await apiData(url('/api/admin/billing'));
    const bars = Object.entries({
      tenants: 'Бизнесы', bookings: 'Записи в этом месяце', aiMessages: 'AI-сообщения',
    }).map(([key, label]) => {
      const u = res.usage[key];
      const unlimited = u.limit === -1;
      const pct = unlimited ? 0 : Math.min(100, Math.round(u.used / Math.max(1, u.limit) * 100));
      return el('div', { className: 'usage' },
        el('div', { className: 'usage-top' },
          el('span', {}, label),
          el('b', {}, unlimited ? `${u.used} · без ограничений` : `${u.used} из ${u.limit}`)),
        el('span', {
          className: `bar${pct >= 90 ? ' hot' : ''}`,
          attrs: { role: 'progressbar', 'aria-valuenow': String(pct), 'aria-valuemin': '0', 'aria-valuemax': '100',
                   'aria-label': `${label}: ${pct}%` },
        }, el('i', { style: `width:${pct}%` })));
    });

    const plans = el('div', { className: 'plans' }, ...res.plans.map((p) => {
      const box = el('div', { className: `plan${p.current ? ' current' : ''}` },
        el('b', {}, p.title), el('span', { className: 'price' }, p.price),
        el('small', {}, p.note),
        el('ul', {},
          el('li', {}, p.limits.tenants === -1 ? 'Бизнесы: без ограничений' : `Бизнесов: ${p.limits.tenants}`),
          el('li', {}, p.limits.bookings === -1 ? 'Записи: без ограничений' : `Записей в месяц: ${p.limits.bookings}`),
          el('li', {}, `AI-сообщений: ${p.limits.aiMessages}`)));
      if (!p.current) {
        const pick = el('button', { className: 'btn btn-secondary', textContent: 'Перейти' });
        pick.onclick = async () => {
          const ok = await confirmDialog({
            title: `Перейти на тариф «${p.title}»?`,
            message: `${p.price}. Лимиты пересчитаются сразу — если текущее потребление их превышает, `
              + 'бот перестанет создавать записи до конца месяца.',
            confirmLabel: 'Перейти',
          });
          if (!ok) return;
          try {
            await apiJson(url('/api/admin/billing'), {
              method: 'PUT', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ plan: p.id, status: 'active' }),
            });
            renderBilling(panel);
            toast('ok', 'Тариф изменён', `Действует «${p.title}»`);
          } catch (e) {
            toast('err', 'Не удалось сменить тариф', e.message || 'Сервер отклонил запрос.');
          }
        };
        box.append(pick);
      } else {
        box.append(el('span', { className: 'current-mark' }, 'текущий'));
      }
      return box;
    }));

    body.replaceChildren(
      el('div', { className: 'card' },
        el('p', { className: 'hint', style: 'margin-bottom:20px' },
          `Тариф «${res.planTitle}» · ${res.price} · период ${res.period}`
          + (res.status === 'active' ? '' : ` · подписка ${res.status}`)),
        ...bars),
      el('div', { className: 'card' }, el('h2', {}, 'Тарифы'),
        el('p', { className: 'hint' }, 'Лимиты считаются суммарно по всем бизнесам аккаунта.'), plans));
  } catch (err) {
    body.replaceChildren(errorState('Не удалось загрузить тариф',
      loadFailure(err), () => renderBilling(panel)));
  }
}

/* ============================== TELEGRAM =============================== */
/* Токен от @BotFather — единственное, что нельзя получить за пользователя:
   OAuth для ботов у Telegram нет. Всё остальное панель делает сама: проверяет
   токен через getMe, а номер чата — самое неудобное поле формы — вычисляет из
   getUpdates после того, как владелец напишет боту «/start». */

function telegramConnectBlock() {
  const box = el('div', { className: 'connect' });
  drawTelegramConnect(box);
  return box;
}

async function drawTelegramConnect(box) {
  let info;
  try {
    info = await apiJson(url('/api/admin/telegram/status'));
  } catch {
    box.replaceChildren(el('span', {}, 'Не удалось проверить подключение Telegram.'));
    return;
  }

  const broken = Boolean(info.degraded);
  box.className = `connect${info.connected && !broken ? ' linked' : ''}${broken ? ' broken' : ''}`;
  const ico = el('div', { className: 'icon' },
    icon(broken ? 'warning' : info.connected ? 'checkCircle' : 'send', { size: 20 }));
  const body = el('div', { className: 'body' });
  const redraw = () => drawTelegramConnect(box);

  if (broken) {
    body.append(el('b', {}, 'Telegram настроен, но недоступен'),
      el('span', {}, info.error || 'Токен больше не действует — подключите бота заново.'));
    const again = el('button', { className: 'btn btn-primary btn-sm' },
      icon('refresh', { size: 15 }), 'Подключить заново');
    again.onclick = () => askTelegramToken(redraw);
    box.replaceChildren(ico, body, again, telegramOffButton(redraw));
    return;
  }

  // Токен есть, чата нет — половина настройки. Уведомления в этом состоянии
  // никуда не уходят, поэтому шаг «связать чат» показываем как незакрытый.
  if (info.hasToken && !info.connected) {
    body.append(el('b', {}, `Бот @${info.bot} подключён — остался один шаг`),
      el('span', {}, 'Откройте чат с ботом, отправьте «/start» и нажмите «Связать чат» — '
        + 'номер чата панель определит сама.'));
    const open = el('a', { className: 'btn btn-secondary btn-sm', href: info.link,
                           target: '_blank', rel: 'noopener' },
      icon('external', { size: 15 }), 'Открыть чат с ботом');
    const link = el('button', { className: 'btn btn-primary btn-sm' },
      icon('checkCircle', { size: 15 }), 'Связать чат');
    link.onclick = () => linkTelegramChat(link, redraw);
    box.replaceChildren(ico, body, open, link, telegramOffButton(redraw));
    return;
  }

  if (info.connected) {
    body.append(el('b', {}, `Telegram подключён — бот @${info.bot}`),
      el('span', {}, 'Уведомления о записях и передача администратору уходят в связанный чат.'));
    const test = el('button', { className: 'btn btn-primary btn-sm' },
      icon('send', { size: 15 }), 'Отправить тест');
    test.onclick = () => testTelegram(test);
    const relink = el('button', { className: 'btn btn-secondary btn-sm' },
      icon('refresh', { size: 15 }), 'Сменить чат');
    relink.onclick = () => linkTelegramChat(relink, redraw);
    box.replaceChildren(ico, body, test, relink, telegramOffButton(redraw));
    return;
  }

  body.append(el('b', {}, 'Telegram не подключён'),
    el('span', {}, 'Бесплатно и без карты: напишите @BotFather команду /newbot, получите токен '
      + 'и вставьте его здесь — имя бота и номер чата панель определит сама.'));
  const connect = el('button', { className: 'btn btn-primary' },
    icon('send', { size: 15 }), 'Подключить Telegram');
  connect.onclick = () => askTelegramToken(redraw);
  box.replaceChildren(ico, body, connect);
}

function askTelegramToken(done) {
  const d = drawer({ title: 'Подключение Telegram', subtitle: 'Бесплатно, карта не нужна' });
  const input = el('input', { type: 'text', placeholder: '123456789:AA…', id: 'tg-token' });
  input.setAttribute('autocomplete', 'off');
  const hint = el('p', { className: 'hint' }, 'Токен виден только серверу и в форму не возвращается.');

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Где взять токен'),
      el('ol', { className: 'steps' },
        el('li', {}, 'Откройте в Telegram чат с @BotFather и отправьте /newbot.'),
        el('li', {}, 'Придумайте имя бота — например, «Demo Salon уведомления».'),
        el('li', {}, 'BotFather пришлёт строку вида 123456789:AA… — это и есть токен.')),
      el('p', { className: 'copy-row' },
        el('a', { href: 'https://t.me/BotFather', target: '_blank', rel: 'noopener' },
          'Открыть @BotFather →'))),
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Токен бота'),
      el('div', { className: 'field' }, el('label', { htmlFor: 'tg-token' }, 'Вставьте строку целиком'), input),
      hint));

  const save = el('button', { className: 'btn btn-primary', textContent: 'Подключить' });
  save.onclick = async () => {
    const token = input.value.trim();
    if (!token) { input.focus(); return; }
    save.disabled = true;
    try {
      const res = await api(url('/api/admin/telegram/connect'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || 'Telegram не принял токен');
      d.close();
      toast('ok', `Бот @${payload.bot} подключён`, 'Остался шаг: отправьте боту «/start» и свяжите чат.');
      done?.();
    } catch (e) {
      hint.textContent = e.message || 'Не удалось подключить';
      hint.style.color = 'var(--c-err)';
      save.disabled = false;
    }
  };
  const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
  cancel.onclick = d.close;
  d.footer.append(save, cancel);
  setTimeout(() => input.focus(), 80);
}

async function linkTelegramChat(btn, done) {
  btn.disabled = true;
  try {
    const res = await api(url('/api/admin/telegram/link'), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Чат не найден');
    toast('ok', 'Чат связан', `Уведомления пойдут в «${payload.chatTitle || payload.chatId}».`);
    done?.();
    await load();
  } catch (e) {
    toast('err', 'Чат не связан', e.message || 'Отправьте боту «/start» и попробуйте снова.',
      { timeout: 12000 });
  } finally {
    btn.disabled = false;
  }
}

async function testTelegram(btn) {
  btn.disabled = true;
  try {
    const res = await api(url('/api/admin/telegram/test'), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Сообщение не ушло');
    toast('ok', 'Сообщение отправлено', 'Проверьте чат с ботом.');
  } catch (e) {
    toast('err', 'Сообщение не ушло', e.message || 'Telegram отклонил запрос.');
  } finally {
    btn.disabled = false;
  }
}

function telegramOffButton(done) {
  const off = el('button', { className: 'btn btn-ghost btn-sm', textContent: 'Отключить' });
  off.onclick = async () => {
    const ok = await confirmDialog({
      title: 'Отключить Telegram?',
      message: 'Уведомления владельцу вернутся в лог сервера. Токен бота будет удалён — '
        + 'для повторного подключения понадобится вставить его заново.',
      confirmLabel: 'Отключить', danger: true,
    });
    if (!ok) return;
    await api(url('/api/admin/telegram/disconnect'), { method: 'POST' });
    toast('ok', 'Telegram отключён', 'Бот больше не пишет владельцу.');
    done?.();
    await load();
  };
  return off;
}

/* ================================ TWILIO =============================== */
/* Подключение одной кнопкой, как у Telegram и AI: раньше здесь стояли четыре
   поля, из которых два — секреты, и ошибка в любом давала молчащий канал.
   Ключи проверяются живым запросом, номера подтягиваются из аккаунта — их не
   нужно набирать руками и ошибаться в формате. */

function twilioConnectBlock() {
  const box = el('div', { className: 'connect' });
  drawTwilio(box);
  return box;
}

async function drawTwilio(box) {
  const redraw = () => drawTwilio(box);
  let info;
  try {
    info = await apiJson(url('/api/admin/twilio/status'));
  } catch {
    box.replaceChildren(el('span', {}, 'Не удалось проверить подключение Twilio.'));
    return;
  }

  const broken = Boolean(info.degraded);
  box.className = `connect${info.connected && !broken ? ' linked' : ''}${broken ? ' broken' : ''}`;
  const ico = el('div', { className: 'icon' },
    icon(broken ? 'warning' : info.connected ? 'checkCircle' : 'send', { size: 20 }));
  const body = el('div', { className: 'body' });

  if (broken) {
    body.append(el('b', {}, 'Twilio настроен, но недоступен'),
      el('span', {}, info.error || 'Ключи больше не действуют — подключите заново.'));
    const again = el('button', { className: 'btn btn-primary btn-sm' },
      icon('refresh', { size: 15 }), 'Подключить заново');
    again.onclick = () => askTwilioKeys(redraw);
    box.replaceChildren(ico, body, again, twilioOffButton(redraw));
    return;
  }

  if (info.connected) {
    const from = info.whatsappFrom || info.smsFrom;
    body.append(el('b', {}, `Twilio подключён — ${info.account}`),
      el('span', {}, from
        ? `Отправитель: ${info.whatsappFrom ? `WhatsApp ${info.whatsappFrom}` : ''}`
          + `${info.whatsappFrom && info.smsFrom ? ' · ' : ''}`
          + `${info.smsFrom ? `SMS ${info.smsFrom}` : ''}`
        : 'Осталось выбрать номер отправителя.'));
    const senders = el('button', { className: 'btn btn-secondary btn-sm' },
      icon('phone', { size: 15 }), from ? 'Сменить номер' : 'Выбрать номер');
    senders.onclick = () => askTwilioSenders(info, redraw);
    const actions = [senders];
    if (from) {
      const test = el('button', { className: 'btn btn-primary btn-sm' },
        icon('send', { size: 15 }), 'Отправить тест');
      test.onclick = () => askTwilioTest();
      actions.unshift(test);
    }
    box.replaceChildren(ico, body, ...actions, twilioOffButton(redraw));
    return;
  }

  body.append(el('b', {}, 'Twilio не подключён'),
    el('span', {}, 'Отсюда уходят подтверждения и напоминания клиентам — WhatsApp и SMS. '
      + 'Нужны Account SID и Auth Token из консоли Twilio.'));
  const connect = el('button', { className: 'btn btn-primary' },
    icon('send', { size: 15 }), 'Подключить Twilio');
  connect.onclick = () => askTwilioKeys(redraw);
  box.replaceChildren(ico, body, connect);
}

function askTwilioKeys(done) {
  const d = drawer({ title: 'Подключение Twilio', subtitle: 'Сообщения клиентам в WhatsApp и SMS' });
  const sid = el('input', { type: 'text', id: 'tw-sid', placeholder: 'AC…' });
  const token = el('input', { type: 'password', id: 'tw-token', placeholder: '••••••••' });
  [sid, token].forEach((i) => i.setAttribute('autocomplete', 'off'));
  const hint = el('p', { className: 'hint' },
    'Ключи проверяются сразу и хранятся только на сервере — в форму не возвращаются.');

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Где взять'),
      el('ol', { className: 'steps' },
        el('li', {}, 'Откройте console.twilio.com — ключи на главной странице.'),
        el('li', {}, 'Account SID начинается с «AC».'),
        el('li', {}, 'Auth Token рядом, под кнопкой «показать».')),
      el('p', { className: 'copy-row' },
        el('a', { href: 'https://console.twilio.com', target: '_blank', rel: 'noopener' },
          'Открыть консоль Twilio →'))),
    el('div', { className: 'block' },
      el('div', { className: 'field' }, el('label', { htmlFor: 'tw-sid' }, 'Account SID'), sid),
      el('div', { className: 'field' }, el('label', { htmlFor: 'tw-token' }, 'Auth Token'), token),
      hint));

  const save = el('button', { className: 'btn btn-primary', textContent: 'Подключить' });
  save.onclick = async () => {
    save.disabled = true;
    const res = await api(url('/api/admin/twilio/connect'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accountSid: sid.value.trim(), authToken: token.value.trim() }),
    });
    const payload = await res.json();
    if (!res.ok) {
      hint.textContent = payload.detail || 'Twilio не принял ключи';
      hint.style.color = 'var(--c-err)';
      save.disabled = false;
      return;
    }
    d.close();
    toast('ok', `Twilio подключён — ${payload.account}`, 'Осталось выбрать номер отправителя.');
    done?.();
  };
  const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
  cancel.onclick = d.close;
  d.footer.append(save, cancel);
  setTimeout(() => sid.focus(), 80);
}

function askTwilioSenders(info, done) {
  const d = drawer({ title: 'Номер отправителя', subtitle: info.account });
  const wa = el('select', { id: 'tw-wa' });
  const sms = el('select', { id: 'tw-sms' });
  const options = (sel, list, current, extra) => {
    sel.append(el('option', { value: '', textContent: '— не использовать —' }));
    if (extra) sel.append(el('option', { value: extra.value, textContent: extra.label }));
    list.forEach((n) => sel.append(el('option', { value: n.number, textContent: n.label === n.number ? n.number : `${n.number} — ${n.label}` })));
    // Номер мог быть введён раньше руками или прийти из песочницы.
    if (current && ![...sel.options].some((o) => o.value === current)) {
      sel.append(el('option', { value: current, textContent: current }));
    }
    sel.value = current || '';
  };
  options(wa, info.numbers, info.whatsappFrom,
          { value: info.sandbox, label: `${info.sandbox} — песочница Twilio` });
  options(sms, info.numbers.filter((n) => n.sms), info.smsFrom);

  const useTwilio = el('input', { type: 'checkbox', id: 'tw-use', checked: true });

  d.body.append(el('div', { className: 'block' },
    el('div', { className: 'field' }, el('label', { htmlFor: 'tw-wa' }, 'WhatsApp-отправитель'), wa),
    el('p', { className: 'hint' }, 'Пока свой номер не одобрен в Meta, шлите из песочницы: '
      + 'она доставляет только тем, кто отправил ей «join …».'),
    el('div', { className: 'field' }, el('label', { htmlFor: 'tw-sms' }, 'SMS-отправитель'), sms),
    el('label', { className: 'check-row', htmlFor: 'tw-use' }, useTwilio,
      el('span', {}, 'Переключить клиентские уведомления на Twilio'))));

  const save = el('button', { className: 'btn btn-primary', textContent: 'Сохранить' });
  save.onclick = async () => {
    save.disabled = true;
    await api(url('/api/admin/twilio/senders'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ whatsappFrom: wa.value, smsFrom: sms.value, useTwilio: useTwilio.checked }),
    });
    d.close();
    toast('ok', 'Отправитель сохранён', useTwilio.checked
      ? 'Клиентские уведомления идут через Twilio.' : 'Канал клиента не менялся.');
    done?.();
    await load();
  };
  const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
  cancel.onclick = d.close;
  d.footer.append(save, cancel);
}

function askTwilioTest() {
  const phone = el('input', { type: 'tel', id: 'tw-to', placeholder: '+598 99 123 456' });
  overlay('Проверка отправки', [{ label: 'Номер получателя', input: phone }], async () => {
    const res = await api(url('/api/admin/twilio/test'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: phone.value.trim() }),
    });
    const payload = await res.json();
    if (!res.ok) return payload.detail || 'Twilio не принял сообщение';
    toast('ok', 'Сообщение отправлено', `Канал: ${payload.channel}. Проверьте телефон.`);
    return '';
  }, { submitLabel: 'Отправить',
       note: 'Уйдёт настоящее сообщение. В песочнице дойдёт только на номер, отправивший «join …».' });
}

function twilioOffButton(done) {
  const off = el('button', { className: 'btn btn-ghost btn-sm', textContent: 'Отключить' });
  off.onclick = async () => {
    const ok = await confirmDialog({
      title: 'Отключить Twilio?',
      message: 'Клиентские уведомления вернутся в лог сервера — клиент перестанет получать '
        + 'подтверждения и напоминания. Ключи будут удалены.',
      confirmLabel: 'Отключить', danger: true,
    });
    if (!ok) return;
    await api(url('/api/admin/twilio/disconnect'), { method: 'POST' });
    toast('ok', 'Twilio отключён', 'Сообщения клиентам теперь только в логе.');
    done?.();
    await load();
  };
  return off;
}

/* ==================== ВНУТРЕННИЕ УВЕДОМЛЕНИЯ =========================== */
/* Кому из своих уходят новые записи. Список людей — тот же, что и вход в
   панель: отдельный справочник контактов разъехался бы с ним, и отключённый
   администратор продолжал бы получать записи. */

const ROLE_LABEL = { owner: 'Владелец', admin: 'Администратор' };

function staffBlock() {
  const box = el('div', { className: 'staff' });
  drawStaff(box);
  return box;
}

async function drawStaff(box) {
  const redraw = () => drawStaff(box);
  let info;
  try {
    info = await apiJson(url('/api/admin/auth/users'));
  } catch {
    box.replaceChildren(el('p', { className: 'hint' }, 'Не удалось загрузить список людей.'));
    return;
  }

  const head = el('div', { className: 'staff-head' },
    el('h3', { className: 'section-title' }, 'Кто получает записи'),
    el('p', { className: 'hint' }, info.botConnected
      ? 'Сообщения уходят ботом салона. Ссылку для привязки отправьте человеку — он нажмёт «Начать».'
      : 'Сначала подключите бота салона — вкладка «Передача администратору».'));

  const rows = info.users.map((u) => {
    const who = el('div', { className: 'staff-who' },
      el('b', {}, u.name || u.email),
      el('span', {}, `${ROLE_LABEL[u.role] ?? u.role} · ${u.email}`));

    const state = el('span', { className: `badge ${u.telegramLinked ? 'ok' : ''}` },
      icon(u.telegramLinked ? 'checkCircle' : 'send', { size: 12 }),
      u.telegramLinked ? 'Telegram привязан' : 'без Telegram');

    const actions = el('div', { className: 'staff-actions' });
    if (info.botConnected && !u.telegramLinked) {
      const copy = el('button', { className: 'btn btn-secondary btn-sm', type: 'button' },
        icon('copy', { size: 15 }), 'Ссылка');
      copy.onclick = () => copyMasterLink(u.link);
      const check = el('button', { className: 'btn btn-primary btn-sm', type: 'button' },
        icon('checkCircle', { size: 15 }), 'Проверить');
      check.onclick = () => linkStaffTelegram(check, u, redraw);
      actions.append(copy, check);
    }
    if (u.telegramLinked) {
      const test = el('button', { className: 'btn btn-secondary btn-sm', type: 'button' },
        icon('send', { size: 15 }), 'Тест');
      test.onclick = () => testStaffTelegram(test, u);
      actions.append(test);
    }

    const menu = actionMenu(
      el('button', { className: 'btn btn-icon', type: 'button',
                     attrs: { 'aria-label': `Действия: ${u.name || u.email}` } },
         icon('more', { size: 16 })),
      [
        { label: u.notifyNewBooking ? 'Не слать записи' : 'Слать записи', icon: 'bell',
          onSelect: () => patchStaff(u.id, { notifyNewBooking: !u.notifyNewBooking }, redraw) },
        u.role === 'admin'
          ? { label: 'Сделать владельцем', icon: 'user',
              onSelect: () => patchStaff(u.id, { role: 'owner' }, redraw) }
          : { label: 'Сделать администратором', icon: 'user',
              onSelect: () => patchStaff(u.id, { role: 'admin' }, redraw) },
        u.telegramLinked
          ? { label: 'Отвязать Telegram', icon: 'x',
              onSelect: () => unlinkStaffTelegram(u, redraw) }
          : null,
        { label: 'Удалить', icon: 'trash', danger: true,
          onSelect: () => removeStaff(u, redraw) },
      ]);

    return el('div', { className: `staff-row${u.isActive ? '' : ' off'}` },
      who, state, actions, menu);
  });

  const add = el('button', { className: 'btn-add', type: 'button' },
    icon('plus', { size: 16 }), 'Добавить человека');
  add.onclick = () => askNewStaff(redraw);

  box.replaceChildren(head, ...rows, add);
}

async function linkStaffTelegram(btn, user, done) {
  btn.disabled = true;
  try {
    const res = await api(url(`/api/admin/auth/users/${user.id}/telegram/link`), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Чат не найден');
    toast('ok', 'Telegram привязан',
      `${user.name || user.email} будет получать новые записи.`);
    done?.();
  } catch (e) {
    toast('err', 'Не привязано', e.message, { timeout: 12000 });
  } finally {
    btn.disabled = false;
  }
}

async function testStaffTelegram(btn, user) {
  btn.disabled = true;
  try {
    const res = await api(url(`/api/admin/auth/users/${user.id}/telegram/test`), { method: 'POST' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || 'Сообщение не ушло');
    toast('ok', 'Сообщение отправлено', `${user.name || user.email} должен увидеть его в чате.`);
  } catch (e) {
    toast('err', 'Сообщение не ушло', e.message);
  } finally {
    btn.disabled = false;
  }
}

async function unlinkStaffTelegram(user, done) {
  await api(url(`/api/admin/auth/users/${user.id}/telegram`), { method: 'DELETE' });
  toast('ok', 'Telegram отвязан', `${user.name || user.email} больше не получает записи.`);
  done?.();
}

async function patchStaff(id, patch, done) {
  const res = await api(url(`/api/admin/auth/users/${id}`), {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
  });
  const payload = await res.json();
  if (!res.ok) { toast('err', 'Не изменено', payload.detail || 'Отказано', { timeout: 10000 }); return; }
  done?.();
}

async function removeStaff(user, done) {
  const ok = await confirmDialog({
    title: `Удалить ${user.name || user.email}?`,
    message: 'Человек потеряет доступ к панели и перестанет получать записи. '
      + 'Записи и расписание не меняются.',
    confirmLabel: 'Удалить', danger: true,
  });
  if (!ok) return;
  const res = await api(url(`/api/admin/auth/users/${user.id}`), { method: 'DELETE' });
  const payload = await res.json();
  if (!res.ok) { toast('err', 'Не удалён', payload.detail || 'Отказано', { timeout: 10000 }); return; }
  toast('ok', 'Удалён', 'Доступ закрыт.');
  done?.();
}

function askNewStaff(done) {
  const d = drawer({ title: 'Новый человек', subtitle: 'Доступ в панель и уведомления о записях' });
  const name = el('input', { type: 'text', id: 'st-name', placeholder: 'Taylor' });
  const email = el('input', { type: 'email', id: 'st-email', placeholder: 'taylor@salon.dev' });
  email.setAttribute('autocomplete', 'off');
  const pass = el('input', { type: 'text', id: 'st-pass', placeholder: 'не короче 10 символов' });
  pass.setAttribute('autocomplete', 'off');
  const role = el('select', { id: 'st-role' },
    el('option', { value: 'admin', textContent: 'Администратор — ведёт салон' }),
    el('option', { value: 'owner', textContent: 'Владелец — плюс подключения и люди' }));
  const hint = el('p', { className: 'hint' },
    'Пароль сообщите человеку — он сможет сменить его в своём профиле.');

  d.body.append(el('div', { className: 'block' },
    el('div', { className: 'field' }, el('label', { htmlFor: 'st-name' }, 'Имя'), name),
    el('div', { className: 'field' }, el('label', { htmlFor: 'st-email' }, 'Почта'), email),
    el('div', { className: 'field' }, el('label', { htmlFor: 'st-pass' }, 'Пароль'), pass),
    el('div', { className: 'field' }, el('label', { htmlFor: 'st-role' }, 'Роль'), role),
    hint));

  const save = el('button', { className: 'btn btn-primary', textContent: 'Добавить' });
  save.onclick = async () => {
    save.disabled = true;
    const res = await api(url('/api/admin/auth/users'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value.trim(), password: pass.value,
                             name: name.value.trim(), role: role.value }),
    });
    const payload = await res.json();
    if (!res.ok) {
      hint.textContent = payload.detail || 'Не удалось добавить';
      hint.style.color = 'var(--c-err)';
      save.disabled = false;
      return;
    }
    d.close();
    toast('ok', 'Человек добавлен', 'Отправьте ему ссылку для привязки Telegram.');
    done?.();
  };
  const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
  cancel.onclick = d.close;
  d.footer.append(save, cancel);
  setTimeout(() => name.focus(), 80);
}

/* ============================== AI-ДИАЛОГ ============================== */
/* Вместо трёх полей («провайдер», «модель», «ключ»), где ошибка в любом даёт
   молчащего бота, — карточки провайдеров. Ключ проверяется до сохранения, а
   модель сверяется со списком доступных: у бесплатных провайдеров имена
   моделей меняются чаще, чем выходят релизы бота. */

function aiConnectBlock() {
  const box = el('div', { className: 'ai-connect' });
  drawAiConnect(box);
  return box;
}

async function drawAiConnect(box) {
  let info;
  try {
    info = await apiJson(url('/api/admin/ai/status'));
  } catch {
    box.replaceChildren(el('span', {}, 'Не удалось проверить подключение AI.'));
    return;
  }
  const redraw = () => drawAiConnect(box);
  const connected = info.enabled && info.hasKey;
  const currentTitle = (info.providers.find((p) => p.id === info.provider) || {}).title || info.provider;

  const broken = Boolean(info.degraded);
  const status = el('div', { className: `connect${connected ? ' linked' : ''}${broken ? ' broken' : ''}` },
    el('div', { className: 'icon' },
      icon(broken ? 'warning' : connected ? 'checkCircle' : 'sparkles', { size: 20 })),
    el('div', { className: 'body' },
      el('b', {}, broken ? 'AI-диалог включён, но ключа нет'
        : connected ? `AI-диалог работает через ${currentTitle}` : 'AI-диалог выключен'),
      el('span', {}, broken
        ? `Провайдер ${currentTitle} выбран, но ключ не сохранён — так бывает после переезда на другой сервер. `
          + 'Бот пока отвечает по кнопкам. Подключите провайдера заново.'
        : connected
        ? `Модель ${info.model}. Она ведёт разговор и вызывает четыре инструмента — к календарю и базе доступа у неё нет.`
        : 'Пока выключен, бот отвечает по кнопкам: услуга → мастер → время. Это рабочий сценарий, просто без свободного диалога.')));
  if (connected) {
    const test = el('button', { className: 'btn btn-primary btn-sm' },
      icon('checkCircle', { size: 15 }), 'Проверить');
    test.onclick = () => testAi(test);
    const off = el('button', { className: 'btn btn-ghost btn-sm', textContent: 'Выключить' });
    off.onclick = async () => {
      const ok = await confirmDialog({
        title: 'Выключить AI-диалог?',
        message: 'Бот вернётся к сценарию по кнопкам. Ключ будет удалён.',
        confirmLabel: 'Выключить', danger: true,
      });
      if (!ok) return;
      await api(url('/api/admin/ai/disconnect'), { method: 'POST' });
      toast('ok', 'AI-диалог выключен', 'Бот работает по кнопкам.');
      redraw();
      await load();
    };
    status.append(test, off);
  }

  const tiles = info.providers.map((p) => {
    const isCurrent = connected && p.id === info.provider;
    const box2 = el('div', { className: `plan${isCurrent ? ' current' : ''}` },
      el('b', {}, p.title),
      el('span', { className: 'price' },
        p.free ? 'Бесплатно' : 'Платно',
        p.recommended ? el('em', { className: 'pick' }, 'рекомендуем') : null),
      el('small', {}, p.note),
      el('ul', {}, el('li', {}, p.freeNote), el('li', {}, `Модель по умолчанию: ${p.defaultModel}`)));
    const connect = el('button', { className: `btn ${isCurrent ? 'btn-secondary' : 'btn-secondary'}` },
      isCurrent ? 'Сменить ключ' : 'Подключить');
    connect.onclick = () => askAiKey(p, redraw);
    box2.append(connect);
    if (isCurrent) box2.append(el('span', { className: 'current-mark' }, 'подключено'));
    return box2;
  });

  box.replaceChildren(status,
    el('h3', { className: 'section-title', style: 'margin-top:20px' }, 'Кем говорит бот'),
    el('p', { className: 'hint' },
      'Первые два варианта бесплатные — ключ выдаётся сразу и без карты. Инструменты '
      + 'одинаковые у всех, разница только в манере речи и лимитах.'),
    el('div', { className: 'plans', style: 'margin-top:16px' }, ...tiles));
}

function askAiKey(provider, done) {
  const d = drawer({ title: `Подключение ${provider.title}`,
                     subtitle: provider.free ? 'Бесплатный тариф' : 'Оплата по расходу' });
  const input = el('input', { type: 'password', placeholder: '••••••••', id: 'ai-key' });
  input.setAttribute('autocomplete', 'off');
  const model = el('input', { type: 'text', value: provider.defaultModel, id: 'ai-model' });
  const hint = el('p', { className: 'hint' }, 'Ключ проверяется у провайдера до сохранения — '
    + 'нерабочий в настройки не попадёт.');

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Где взять ключ'),
      el('ol', { className: 'steps' },
        el('li', {}, `Откройте страницу ключей ${provider.title} и войдите в аккаунт.`),
        el('li', {}, 'Создайте новый ключ — он показывается один раз, скопируйте сразу.'),
        el('li', {}, 'Вставьте его сюда: ключ хранится на сервере и обратно в форму не возвращается.')),
      el('p', { className: 'copy-row' },
        el('a', { href: provider.keyUrl, target: '_blank', rel: 'noopener' },
          `Открыть ${provider.title} →`))),
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Ключ и модель'),
      el('div', { className: 'field' }, el('label', { htmlFor: 'ai-key' }, 'API-ключ'), input),
      el('div', { className: 'field' }, el('label', { htmlFor: 'ai-model' }, 'Модель'), model),
      hint));

  const save = el('button', { className: 'btn btn-primary', textContent: 'Подключить' });
  save.onclick = async () => {
    const apiKey = input.value.trim();
    if (!apiKey) { input.focus(); return; }
    save.disabled = true;
    const stop = toast('info', 'Проверяю ключ…', `Спрашиваю у ${provider.title}.`, { timeout: 0 });
    try {
      const res = await api(url('/api/admin/ai/connect'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: provider.id, apiKey, model: model.value.trim() }),
      });
      const payload = await res.json();
      stop();
      if (!res.ok) throw new Error(payload.detail || 'Ключ не принят');
      d.close();
      toast('ok', 'AI-диалог подключён', `${provider.title}, модель ${payload.model}.`);
      done?.();
      await load();
    } catch (e) {
      stop();
      hint.textContent = e.message || 'Не удалось подключить';
      hint.style.color = 'var(--c-err)';
      save.disabled = false;
    }
  };
  const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
  cancel.onclick = d.close;
  d.footer.append(save, cancel);
  setTimeout(() => input.focus(), 80);
}

/** Живой запрос к модели: валидный ключ ещё не значит работающий диалог. */
async function testAi(btn) {
  btn.disabled = true;
  const stop = toast('info', 'Спрашиваю модель…', 'Отправляю короткий запрос.', { timeout: 0 });
  try {
    const res = await api(url('/api/admin/ai/test'), { method: 'POST' });
    const payload = await res.json();
    stop();
    if (!res.ok) throw new Error(payload.detail || 'Модель не ответила');
    toast('ok', 'Модель отвечает', `Ответ: «${payload.answer || '—'}»`);
  } catch (e) {
    stop();
    toast('err', 'Модель не ответила', e.message || 'Провайдер отклонил запрос.', { timeout: 14000 });
  } finally {
    btn.disabled = false;
  }
}

/* ============================== БАЗА ДАННЫХ ============================= */
/* Раздел не спрашивает строку подключения и не предлагает выбрать хранилище:
   база одна на весь сервис, её адрес задаётся переменной окружения на сервере,
   и владелец салона всё равно не может её сменить из панели. Форма, которая
   притворялась выбором, только пугала — вместо неё здесь видно, жива ли база,
   сколько в ней данных и куда можно переехать, если сервису станет тесно. */

/** Бесплатные хранилища, на которые сервис умеет переезжать: у всех Postgres,
    поэтому переезд — это смена DATABASE_URL, а не переписывание кода. */
const DB_PROVIDERS = [
  {
    id: 'service', title: 'База сервиса', price: 'Входит в тариф',
    note: 'Postgres рядом с ботом, бэкап раз в сутки. Ничего настраивать не нужно.',
    limits: ['Место — сколько на сервере', 'Резервные копии автоматически', 'Отдельная база каждому салону не нужна'],
  },
  {
    id: 'Supabase', title: 'Supabase', price: 'Бесплатный тариф', url: 'https://supabase.com/dashboard/projects',
    note: 'Postgres в облаке с веб-панелью. Подходит, если данные должны жить отдельно от сервера.',
    limits: ['500 МБ на проект', 'Своя панель для просмотра данных', 'Проект засыпает после недели простоя'],
    steps: [
      'Создайте проект на supabase.com — регистрация по почте, карта не нужна.',
      'Project Settings → Database → Connection string → режим Session pooler.',
      'Скопируйте строку и подставьте в неё пароль проекта вместо [YOUR-PASSWORD].',
    ],
  },
  {
    id: 'Neon', title: 'Neon', price: 'Бесплатный тариф', url: 'https://console.neon.tech',
    note: 'Postgres, который сам засыпает без нагрузки. Быстрее всего заводится.',
    limits: ['0,5 ГБ на проект', 'Ветки базы для тестов', 'Просыпается за пару секунд'],
    steps: [
      'Создайте проект на neon.tech — вход через GitHub или почту.',
      'На главной проекта нажмите Connect и выберите Connection string.',
      'Скопируйте строку целиком — пароль уже внутри неё.',
    ],
  },
];

const fmtBytes = (n) => {
  if (!n) return '—';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let value = n; let i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
  return `${value < 10 && i ? value.toFixed(1) : Math.round(value)} ${units[i]}`;
};

async function renderDatabase(panel) {
  const head = pageHead('База данных', 'Где лежат записи, диалоги и напоминания.');
  const body = el('div', {}, skeletonCards(2));
  panel.replaceChildren(head, body);
  try {
    const info = await apiData(url('/api/admin/database/status'));
    body.replaceChildren(dbStatusCard(info, panel), dbProvidersCard(info));
  } catch (err) {
    body.replaceChildren(errorState('Не удалось проверить базу',
      loadFailure(err), () => renderDatabase(panel)));
  }
}

function dbStatusCard(info, panel) {
  const external = info.provider !== 'service' && info.provider !== 'file';
  const where = info.provider === 'service' ? 'На сервере рядом с ботом'
    : info.provider === 'file' ? 'Локальный файл — только для разработки'
    : `Внешнее хранилище: ${info.provider}`;

  const box = el('div', { className: `connect${info.ok ? ' linked' : ' broken'}` },
    el('div', { className: 'icon' }, icon(info.ok ? 'checkCircle' : 'warning', { size: 20 })),
    el('div', { className: 'body' },
      el('b', {}, info.ok ? 'База подключена и отвечает' : 'База недоступна'),
      el('span', {}, info.ok
        ? `${where}. ${info.version || 'Postgres'} · ${info.name || 'база'} · занято ${fmtBytes(info.sizeBytes)}.`
        : info.error || 'Сервис не смог обратиться к базе — записи сейчас не сохраняются.')));

  const check = el('button', { className: 'btn btn-primary btn-sm' },
    icon('checkCircle', { size: 15 }), 'Проверить связь');
  check.onclick = () => checkDatabase(check);
  const again = el('button', { className: 'btn btn-secondary btn-sm' },
    icon('refresh', { size: 15 }), 'Обновить');
  again.onclick = () => renderDatabase(panel);
  box.append(check, again);

  const counts = info.counts ?? {};
  const tiles = [
    { label: 'Записи', value: counts.bookings ?? 0, note: 'визиты этого салона', icon: 'list', cls: '' },
    { label: 'Диалоги', value: counts.conversations ?? 0, note: 'переписки с ботом', icon: 'chat', cls: '' },
    { label: 'Напоминания', value: counts.notifications ?? 0, note: 'в очереди и отправленные', icon: 'bell', cls: '' },
    { label: 'Объём базы', value: fmtBytes(info.sizeBytes), note: 'все салоны вместе', icon: 'database', cls: 'accent' },
  ];
  const kpis = el('div', { className: 'kpis' }, ...tiles.map((t) => el('div', { className: `kpi ${t.cls}` },
    el('div', { className: 'kpi-top' }, icon(t.icon, { size: 14 }), el('span', { className: 'kpi-label' }, t.label)),
    el('b', {}, String(t.value)), el('small', {}, t.note))));

  return el('div', { className: 'card' },
    el('p', { className: 'hint', style: 'margin-bottom:20px' },
      'Записи, диалоги и настройки всех салонов лежат в одной базе — она уже подключена, '
      + 'вводить ничего не нужно. Двойную запись на одно время база не пропустит: это её '
      + 'собственное правило, а не проверка в коде.'),
    box, kpis,
    // Обещать бэкап можно только про базу сервиса: копии снимает соседний
    // контейнер, до внешней базы и до локального файла он не дотягивается.
    info.provider === 'service' ? el('p', { className: 'hint' },
      'Резервная копия снимается автоматически раз в сутки и хранится две недели.') : null,
    external ? el('p', { className: 'hint' },
      'База внешняя — резервные копии настраиваются на стороне провайдера.') : null);
}

/** Настоящая проверка: сервис пишет во временную таблицу и откатывает запись.
    «Сервер ответил» ничего не доказывает — том мог быть смонтирован на чтение. */
async function checkDatabase(btn) {
  btn.disabled = true;
  const stop = toast('info', 'Проверяю базу…', 'Пробую записать и прочитать.', { timeout: 0 });
  try {
    const res = await apiJson(url('/api/admin/database/check'), { method: 'POST' });
    stop();
    if (res.ok) toast('ok', 'База работает', `Запись и чтение прошли за ${res.latencyMs} мс.`);
    else toast('err', 'База не отвечает', res.error || 'Проверка не прошла.', { timeout: 14000 });
  } catch (e) {
    stop();
    toast('err', 'Проверка не прошла', e.message || 'Сервер отклонил запрос.');
  } finally {
    btn.disabled = false;
  }
}

function dbProvidersCard(info) {
  const tiles = DB_PROVIDERS.map((p) => {
    const current = p.id === info.provider || (p.id === 'service' && info.provider === 'file');
    const box = el('div', { className: `plan${current ? ' current' : ''}` },
      el('b', {}, p.title),
      el('span', { className: 'price' }, p.price),
      el('small', {}, p.note),
      el('ul', {}, ...p.limits.map((line) => el('li', {}, line))));
    if (current) box.append(el('span', { className: 'current-mark' }, 'подключено'));
    else {
      const how = el('button', { className: 'btn btn-secondary' }, 'Как подключить');
      how.onclick = () => dbProviderDrawer(p);
      box.append(how);
    }
    return box;
  });

  return el('div', { className: 'card' },
    el('h2', {}, 'Куда можно переехать'),
    el('p', { className: 'hint' },
      'Все варианты — обычный Postgres, поэтому переезд не требует правок в коде: сервис '
      + 'достаточно перезапустить с новым адресом базы. Менять хранилище есть смысл, только '
      + 'если данные должны жить отдельно от сервера.'),
    el('div', { className: 'plans', style: 'margin-top:16px' }, ...tiles));
}

/** Инструкция вместо кнопки «подключить одним нажатием»: сменить базу на лету
    нельзя — адрес читают и API, и воркер напоминаний при старте, а данные сами
    не переезжают. Честные три шага лучше кнопки, которая половину не делает. */
function dbProviderDrawer(provider) {
  const d = drawer({ title: `Переезд на ${provider.title}`, subtitle: provider.price });
  const envLine = 'DATABASE_URL=postgresql://…';

  const copy = el('button', { className: 'btn btn-secondary' }, icon('copy', { size: 15 }), 'Скопировать имя переменной');
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText('DATABASE_URL');
      toast('ok', 'Скопировано', 'Вставьте в Environment Variables на сервере.');
    } catch {
      toast('err', 'Не удалось скопировать', 'Имя переменной — DATABASE_URL.');
    }
  };

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Что сделать у провайдера'),
      el('ol', { className: 'steps' }, ...(provider.steps ?? []).map((s) => el('li', {}, s))),
      provider.url
        ? el('p', { className: 'copy-row' },
          el('a', { href: provider.url, target: '_blank', rel: 'noopener' }, `Открыть ${provider.title} →`))
        : null),
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Что сделать на сервере'),
      el('ol', { className: 'steps' },
        el('li', {}, 'Coolify → сервис бота → Environment Variables → замените DATABASE_URL на новую строку.'),
        el('li', {}, 'Перезапустите сервис: миграции создадут таблицы в пустой базе сами.'),
        el('li', {}, 'Вернитесь сюда и нажмите «Проверить связь».')),
      el('pre', { className: 'snippet', style: 'margin-top:12px' }, envLine),
      el('div', { className: 'copy-row' }, copy)),
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'О чём предупредить заранее'),
      el('p', { className: 'hint' },
        'Записи и диалоги не переезжают сами — новая база стартует пустой. Данные переносят '
        + 'дампом (pg_dump старой базы → psql в новую) до перезапуска сервиса. Пока адрес не '
        + 'сменён на сервере, эта страница продолжает показывать старую базу.')));

  const done = el('button', { className: 'btn btn-primary', textContent: 'Понятно' });
  done.onclick = d.close;
  d.footer.append(done);
}

/* ============================== GOOGLE ================================= */

function googleConnectBlock() {
  const box = el('div', { className: 'connect' });
  drawGoogleConnect(box);
  return box;
}

async function drawGoogleConnect(box) {
  let info = googleStatus;
  try {
    if (!info) info = googleStatus = await apiJson(url('/api/admin/google/status'));
  } catch {
    box.replaceChildren(el('span', {}, 'Не удалось проверить подключение Google.'));
    return;
  }

  const body = el('div', { className: 'body' });
  const broken = Boolean(info.degraded);
  box.className = `connect${info.connected && !broken ? ' linked' : ''}${broken ? ' broken' : ''}`;
  const ico = el('div', { className: 'icon' },
    icon(broken ? 'warning' : info.connected ? 'checkCircle' : 'calendar', { size: 20 }));

  // Настроен, но не работает — отдельное состояние. Иначе сломанная интеграция
  // выглядит как «календарь просто не подключали», и её никто не чинит.
  if (broken) {
    body.append(
      el('b', {}, 'Google Calendar настроен, но недоступен'),
      el('span', {}, info.error || 'Подключение не удалось — записи пока никуда не уходят.'),
    );
    const again = el('button', { className: 'btn btn-primary btn-sm' },
      icon('refresh', { size: 15 }), 'Подключить заново');
    again.onclick = () => { googleStatus = null; drawGoogleConnect(box); };
    box.replaceChildren(ico, body, again, disconnectButton());
    return;
  }

  if (info.connected) {
    body.append(
      el('b', {}, 'Google Calendar подключён'),
      el('span', {}, info.account
        ? `Аккаунт ${info.account}. Записи создаются в выбранных календарях мастеров.`
        : 'Записи создаются в выбранных календарях мастеров.'),
    );
    const verify = el('button', { className: 'btn btn-primary btn-sm' },
      icon('checkCircle', { size: 15 }), 'Проверить связь');
    verify.onclick = () => verifyGoogle(verify);
    const refresh = el('button', { className: 'btn btn-secondary btn-sm' },
      icon('refresh', { size: 15 }), 'Обновить календари');
    refresh.onclick = () => loadCalendars(true);
    box.replaceChildren(ico, body, verify, refresh, disconnectButton());
    loadCalendars();
    return;
  }

  body.append(
    el('b', {}, 'Google Calendar не подключён'),
    el('span', {}, info.hasClientCredentials
      ? 'Нажмите «Войти через Google» и выберите аккаунт салона — доступ сохранится автоматически.'
      : 'Сначала нужен доступ приложения к Google: это делается один раз на весь сервис. '
        + 'Нажмите «Ввести доступ приложения» — там инструкция на три шага.'),
  );

  // Без Client ID и Secret входить некуда: сначала карточка просит их, и просит
  // отдельной кнопкой, а не полем в форме — форма их не сохраняла.
  if (!info.hasClientCredentials) {
    const setup = el('button', { className: 'btn btn-primary' },
      icon('google', { size: 15 }), 'Ввести доступ приложения');
    setup.onclick = () => askGoogleCredentials(info.redirectUri);
    box.replaceChildren(ico, body, setup);
    return;
  }

  const connect = el('button', { className: 'btn btn-primary' },
    icon('google', { size: 15 }), 'Войти через Google');
  connect.onclick = () => {
    const w = window.open(url('/api/admin/google/start'), 'google-auth', 'width=520,height=680');
    if (!w) { location.href = url('/api/admin/google/start'); return; }
    window.addEventListener('message', async (e) => {
      if (e.data?.google === undefined) return;
      googleStatus = null; googleCalendars = [];
      toast('ok', 'Google Calendar подключён', 'Выберите календари мастеров в разделе «Мастера».');
      await load();
    }, { once: true });
  };

  box.replaceChildren(ico, body, connect);
}

/** Client ID и Secret из Google Cloud Console. Отдельная панель, а не поля в
    форме: сохранение конфигурации проверяет её целиком, и незаконченное
    подключение Google запирало сохранение всей панели. */
function askGoogleCredentials(redirectUri) {
  const d = drawer({ title: 'Доступ приложения к Google', subtitle: 'Настраивается один раз' });
  const id = el('input', { type: 'text', placeholder: '1234567890-abc.apps.googleusercontent.com', id: 'g-id' });
  const secret = el('input', { type: 'password', placeholder: '••••••••', id: 'g-secret' });
  [id, secret].forEach((i) => i.setAttribute('autocomplete', 'off'));
  const hint = el('p', { className: 'hint' }, 'Secret хранится на сервере и обратно в форму не возвращается.');

  const copy = el('button', { className: 'btn btn-secondary' }, icon('copy', { size: 15 }), 'Скопировать Redirect URI');
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(redirectUri);
      toast('ok', 'Скопировано', 'Вставьте в Authorized redirect URIs.');
    } catch {
      toast('err', 'Не удалось скопировать', 'Выделите адрес вручную.');
    }
  };

  d.body.append(
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Что сделать в Google Cloud Console'),
      el('ol', { className: 'steps' },
        el('li', {}, 'APIs & Services → Library → включите Google Calendar API.'),
        el('li', {}, 'Credentials → Create credentials → OAuth client ID → тип «Web application».'),
        el('li', {}, 'В Authorized redirect URIs вставьте адрес ниже и сохраните — Google покажет Client ID и Secret.')),
      el('pre', { className: 'snippet', style: 'margin-top:12px' }, redirectUri),
      el('div', { className: 'copy-row' }, copy,
        el('a', { href: 'https://console.cloud.google.com/apis/credentials', target: '_blank', rel: 'noopener' },
          'Открыть Google Cloud Console →'))),
    el('div', { className: 'block' },
      el('h3', { className: 'section-title' }, 'Доступ приложения'),
      el('div', { className: 'field' }, el('label', { htmlFor: 'g-id' }, 'Client ID'), id),
      el('div', { className: 'field' }, el('label', { htmlFor: 'g-secret' }, 'Client Secret'), secret),
      hint));

  const save = el('button', { className: 'btn btn-primary', textContent: 'Сохранить' });
  save.onclick = async () => {
    if (!id.value.trim() || !secret.value.trim()) { (id.value.trim() ? secret : id).focus(); return; }
    save.disabled = true;
    try {
      const res = await api(url('/api/admin/google/credentials'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientId: id.value.trim(), clientSecret: secret.value.trim() }),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || 'Не удалось сохранить');
      d.close();
      toast('ok', 'Доступ сохранён', 'Теперь нажмите «Войти через Google».');
      await refreshGoogleBlock();
    } catch (e) {
      hint.textContent = e.message || 'Не удалось сохранить';
      hint.style.color = 'var(--c-err)';
      save.disabled = false;
    }
  };
  const cancel = el('button', { className: 'btn btn-secondary', textContent: 'Отмена' });
  cancel.onclick = d.close;
  d.footer.append(save, cancel);
  setTimeout(() => id.focus(), 80);
}

function disconnectButton() {
  const off = el('button', { className: 'btn btn-ghost btn-sm', textContent: 'Отключить' });
  off.onclick = async () => {
    const ok = await confirmDialog({
      title: 'Отключить Google Calendar?',
      message: 'Бот вернётся в демо-режим и перестанет создавать события. Существующие записи в базе останутся.',
      confirmLabel: 'Отключить', danger: true,
    });
    if (!ok) return;
    await api(url('/api/admin/google/disconnect'), { method: 'POST' });
    googleStatus = null; googleCalendars = [];
    toast('ok', 'Google Calendar отключён', 'Бот работает в демо-режиме.');
    await load();
  };
  return off;
}

/** Круговой тест: событие создаётся в календаре каждого мастера и сразу удаляется.
    «Подключено» само по себе ничего не доказывает — календарь мог быть не расшарен. */
async function verifyGoogle(btn) {
  btn.disabled = true;
  const stop = toast('info', 'Проверяю связь с календарями…', 'Создаю и удаляю тестовое событие.', { timeout: 0 });
  try {
    const res = await apiJson(url('/api/admin/google/verify'), { method: 'POST' });
    stop();
    const bad = (res.masters ?? []).filter((m) => !m.ok);
    if (res.ok) {
      toast('ok', 'Связь работает',
        `Событие создано и удалено во всех календарях (${res.masters.length}).`);
    } else if (bad.length) {
      toast('err', `Не пишется в календари: ${bad.length}`,
        bad.map((m) => `${m.master}: ${m.detail}`).join('\n'), { timeout: 14000 });
    } else {
      toast('warn', 'Проверять нечего', 'В салоне нет мастеров.');
    }
  } catch (e) {
    stop();
    toast('err', 'Проверка не прошла', e.message || 'Сервер отклонил запрос.');
  } finally {
    btn.disabled = false;
  }
}

/** Перерисовать блок подключения по свежему статусу (после сохранения кредов). */
async function refreshGoogleBlock() {
  const box = document.querySelector('[data-panel="integration"] .connect');
  if (!box) return;
  googleStatus = null;
  await drawGoogleConnect(box);
}

/** Филиалы для формы мастера. Их ведёт экран «Платформа», а не форма настроек. */
async function loadLocations() {
  try {
    const res = await api(url('/api/admin/locations'));
    if (!res.ok) return;
    salonLocations = (await res.json()).locations ?? [];
  } catch { /* без списка поле останется текстовым — не критично */ }
}

async function loadCalendars(force = false) {
  if (googleCalendars.length && !force) return;
  try {
    const res = await api(url('/api/admin/google/calendars'));
    if (!res.ok) return;
    googleCalendars = (await res.json()).calendars ?? [];
    if (force) {
      redrawMasters();
      toast('ok', 'Список календарей обновлён', `Найдено календарей: ${googleCalendars.length}`);
    }
  } catch { /* список календарей — удобство, не критичный путь */ }
}

/* ============================== ВИДЖЕТ И .ENV =========================== */

async function renderEmbed(panel) {
  const head = pageHead('Виджет', 'Код вставки чата записи на сайт салона.');
  const body = el('div', { className: 'card' }, el('span', { className: 'skel skel-line', style: 'height:60px' }));
  panel.replaceChildren(head, body);
  try {
    const info = await apiData(url(`/api/admin/embed?origin=${encodeURIComponent(location.origin)}`));
    const copy = el('button', { className: 'btn btn-secondary' }, icon('copy', { size: 15 }), 'Скопировать');
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(info.snippet);
        toast('ok', 'Код скопирован', 'Вставьте его перед закрывающим тегом </body>.');
      } catch {
        toast('err', 'Не удалось скопировать', 'Выделите код вручную.');
      }
    };
    body.replaceChildren(
      el('p', { className: 'hint' },
        `Вставьте этот тег на сайт бизнеса «${current()?.title ?? tenant}» — перед закрывающим </body>. `
        + 'Виджет заберёт услуги, мастеров и режим работы из этих настроек.'),
      el('pre', { className: 'snippet', style: 'margin-top:16px' }, info.snippet),
      el('div', { className: 'copy-row' }, copy,
        el('a', { href: info.demo, target: '_blank', rel: 'noopener' },
          'Открыть демо-страницу →')),
      el('p', { className: 'hint', style: 'margin-top:16px' },
        `Код бизнеса: ${info.tenant}. Он же подставляется в API-запросы виджета, поэтому один сервис `
        + 'обслуживает сколько угодно салонов, не смешивая их записи.'));
  } catch (err) {
    body.replaceChildren(errorState('Не удалось получить код встраивания',
      loadFailure(err), () => renderEmbed(panel)));
  }
}

/* ============================== CRM И ДЕНЬГИ =========================== */

const money = (value, currency = 'UYU') => `${Number(value || 0).toLocaleString('ru-RU')} ${currency}`;
const simpleTable = (headers, rows) => el('div', { className: 'table-wrap' },
  el('div', { className: 'table-scroll' }, el('table', { className: 'data' },
    el('thead', {}, el('tr', {}, ...headers.map((h) => el('th', {}, h)))),
    el('tbody', {}, ...rows.map((row) => el('tr', {}, ...row.map((cell) => el('td', {}, cell))))))));

async function renderClients(panel) {
  const head = pageHead('Клиенты', 'Единая карточка, история визитов, LTV, согласие и сегменты.');
  // Клиента заводят и до первой записи: пришёл без записи, позвонил, ходит
  // давно. Ждать, пока он запишется через виджет, чтобы появилась карточка,
  // значит вести заметки о постоянных клиентах в тетради.
  const add = el('button', { className: 'btn btn-primary' }, icon('plus', { size: 15 }), 'Добавить клиента');
  add.onclick = () => newClient(panel);
  // Переезд из чужой системы: у DIKIDI и YCLIENTS база выгружается в Excel, и
  // без загрузки к нам салон просто не переедет — а без выгрузки не уедет.
  const upload = el('button', { className: 'btn btn-secondary' }, icon('inbox', { size: 15 }), 'Импорт');
  upload.onclick = () => importClients(panel);
  const download = el('a', {
    className: 'btn btn-secondary', href: url('/api/admin/clients/export'), download: '',
  }, icon('external', { size: 15 }), 'Экспорт');
  // История визитов — отдельным файлом и отдельной кнопкой: у неё свои колонки
  // и своя цена ошибки, а сваливать два разных формата в один диалог значит
  // объяснять владельцу, почему его файл «не подошёл».
  const visits = el('button', { className: 'btn btn-secondary' }, icon('list', { size: 15 }), 'Импорт визитов');
  visits.onclick = () => importVisits(panel);
  head.querySelector('.tools').append(upload, visits, download, add);
  const body = el('div', {}); panel.replaceChildren(head, body); body.append(skeletonCards(4), skeletonTable());
  try {
    const [payload, retention] = await Promise.all([
      apiJson(url('/api/admin/clients')), apiJson(url('/api/admin/retention')),
    ]);
    const rows = payload.clients || [];
    body.replaceChildren(
      el('div', { className: 'kpis' },
        ...[['Клиентов', retention.clients], ['Повторных', retention.repeat],
          ['Возвращаемость', `${retention.repeatRate}%`], ['Средний LTV', money(retention.averageLtv)]
        ].map(([label, value]) => el('div', { className: 'kpi' }, el('span', { className: 'kpi-label' }, label), el('b', {}, String(value))))),
      rows.length ? simpleTable(['Клиент', 'Телефон', 'Визиты', 'Неявки', 'LTV', 'Баллы', ''], rows.map((c) => [
        c.name, c.phone, String(c.visits), String(c.noShows), money(c.ltv), String(c.loyalty),
        (() => { const btn = el('button', { className: 'btn btn-secondary btn-sm', textContent: 'Открыть' }); btn.onclick = () => openClient(c, panel); return btn; })(),
      ])) : emptyState('users', 'Клиентов пока нет',
        'Карточка появляется после первой записи — или заведите её кнопкой «Добавить клиента».'),
    );
  } catch (e) { body.replaceChildren(errorState('Не удалось загрузить клиентов', e.message, () => renderClients(panel))); }
}

/* Загрузка базы из CSV. Сначала предпросмотр — чужой файл всегда грязный, и
   владелец должен увидеть, что именно приедет, до того как оно приедет. */

const IMPORT_ACTION = { created: 'новый', updated: 'обновится', rejected: 'пропущен' };

function importClients(panel) {
  const d = drawer({ title: 'Импорт клиентов', subtitle: 'CSV из DIKIDI, YCLIENTS или Excel' });
  const file = el('input', { type: 'file', accept: '.csv,text/csv,text/plain' });
  const hint = el('small', {},
    'Нужна колонка с телефоном — «Телефон», «phone» или «teléfono». Имя, язык, заметки, '
    + 'теги и согласие подхватятся, если они есть. Точка с запятой вместо запятой — тоже нормально.');
  const report = el('div', {});
  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field wide' }, el('label', {}, 'Файл'), file, hint)), report);

  const apply = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Импортировать');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  apply.disabled = true;
  d.footer.append(cancel, apply);

  let text = '';
  file.onchange = async () => {
    const chosen = file.files?.[0];
    if (!chosen) return;
    text = await chosen.text();
    report.replaceChildren(el('p', { className: 'hint' }, 'Считаем строки…'));
    const preview = await postImport(text, false);
    if (!preview) { apply.disabled = true; return; }
    apply.disabled = !(preview.created + preview.updated);
    drawImportReport(report, preview);
  };

  apply.onclick = async () => {
    apply.disabled = true;
    const done = await postImport(text, true);
    if (!done) { apply.disabled = false; return; }
    d.close();
    toast('ok', 'База загружена',
      `Новых: ${done.created}, обновлено: ${done.updated}, пропущено: ${done.rejected}`);
    renderClients(panel);
  };
}

async function postImport(text, commit, path = '/api/admin/clients/import') {
  const res = await api(url(path), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csv: text, commit }),
  });
  const payload = await res.json().catch(() => ({}));
  if (res.ok) return payload;
  toast('err', 'Файл не подошёл',
    typeof payload.detail === 'string' ? payload.detail : 'Проверьте колонки.');
  return null;
}

function drawImportReport(box, preview) {
  const kpi = (label, value) => el('div', { className: 'kpi' },
    el('span', { className: 'kpi-label' }, label), el('b', {}, String(value)));
  // Сервер уже отдал отклонённые первыми и обрезал длинный список.
  const rows = preview.rows || [];
  box.replaceChildren(
    el('div', { className: 'kpis', style: 'margin-top:16px' },
      kpi('Новых', preview.created), kpi('Обновится', preview.updated),
      kpi('Пропущено', preview.rejected)),
    simpleTable(['Строка', 'Имя', 'Телефон', 'Что будет'], rows.slice(0, 200).map((r) => [
      String(r.line), r.name || '—', r.phone || '—',
      r.reason ? `${IMPORT_ACTION[r.action]}: ${r.reason}` : IMPORT_ACTION[r.action],
    ]).slice(0, 500)),
    preview.truncated
      ? el('p', { className: 'hint' },
          `Показаны первые ${rows.length} строк, всего в файле ${preview.total}. `
          + 'Счётчики выше — по всему файлу.')
      : null,
  );
}

/* История визитов из чужой системы. Отдельно от базы клиентов: там ключ —
   телефон, здесь — телефон, дата и время, и без времени история складывается в
   одну минуту, где её отвергает индекс слота. */

function importVisits(panel) {
  const d = drawer({ title: 'Импорт истории визитов',
                     subtitle: 'Прошлые визиты: LTV, сегменты и возвращаемость с первого дня' });
  const file = el('input', { type: 'file', accept: '.csv,text/csv,text/plain' });
  const hint = el('small', {},
    'Нужны телефон, дата и время визита. Услуга и мастер — по названиям из справочника; '
    + 'у салона с одним мастером эти колонки можно не заполнять. Сумма и статус '
    + '(«выполнена», «не пришёл») подхватятся, если есть.');
  // Главный страх при переезде — что импорт разошлёт напоминания о прошлогодних
  // визитах. Он не разошлёт, и сказать об этом надо до загрузки, а не после.
  const calm = el('p', { className: 'hint' },
    'Клиентам ничего не уходит: импортированные визиты не попадают ни в календарь, '
    + 'ни в очередь напоминаний.');
  const report = el('div', {});
  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field wide' }, el('label', {}, 'Файл'), file, hint)), calm, report);

  const apply = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Загрузить историю');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  apply.disabled = true;
  d.footer.append(cancel, apply);

  let text = '';
  file.onchange = async () => {
    const chosen = file.files?.[0];
    if (!chosen) return;
    text = await chosen.text();
    report.replaceChildren(el('p', { className: 'hint' }, 'Считаем строки…'));
    const preview = await postImport(text, false, '/api/admin/visits/import');
    if (!preview) { apply.disabled = true; return; }
    apply.disabled = !preview.created;
    drawVisitsReport(report, preview);
  };

  apply.onclick = async () => {
    apply.disabled = true;
    const done = await postImport(text, true, '/api/admin/visits/import');
    if (!done) { apply.disabled = false; return; }
    d.close();
    toast('ok', 'История загружена',
      `Визитов: ${done.created}, пропущено: ${done.rejected}`);
    renderClients(panel);
  };
}

function drawVisitsReport(box, preview) {
  const kpi = (label, value) => el('div', { className: 'kpi' },
    el('span', { className: 'kpi-label' }, label), el('b', {}, String(value)));
  const rows = preview.rows || [];
  const unmatched = preview.unmatched || {};
  const missing = [
    (unmatched.services || []).length ? `услуги: ${unmatched.services.join(', ')}` : '',
    (unmatched.masters || []).length ? `мастера: ${unmatched.masters.join(', ')}` : '',
  ].filter(Boolean).join('; ');

  box.replaceChildren(
    el('div', { className: 'kpis', style: 'margin-top:16px' },
      kpi('Визитов', preview.created), kpi('Пропущено', preview.rejected),
      kpi('Всего строк', preview.total)),
    // Несопоставленные названия — самая частая причина отказа, и чинится она
    // не в файле, а в справочнике: добавить услугу или переименовать мастера.
    missing ? el('p', { className: 'hint' },
      `Нет в справочнике — ${missing}. Заведите их в «Услугах» и «Мастерах» или `
      + 'исправьте названия в файле, иначе эти строки не заедут.') : null,
    simpleTable(['Строка', 'Клиент', 'Когда', 'Услуга', 'Мастер', 'Что будет'],
      rows.slice(0, 200).map((r) => [
        String(r.line), r.name || r.phone || '—', r.when || '—',
        r.service || '—', r.master || '—',
        r.reason ? `пропущен: ${r.reason}` : 'новый',
      ])),
    preview.truncated
      ? el('p', { className: 'hint' },
          `Показаны первые ${rows.length} строк, всего в файле ${preview.total}. `
          + 'Счётчики выше — по всему файлу.')
      : null,
  );
}

/** Карточка клиента вручную. Телефон — ключ: по нему карточка потом сойдётся с записями. */
function newClient(panel) {
  const d = drawer({ title: 'Новый клиент', subtitle: 'Появится в списке и подхватит будущие записи' });
  const name = el('input', { type: 'text', placeholder: 'Имя клиента' });
  const phone = el('input', { type: 'tel', placeholder: '+598 …' });
  const lang = el('select', {},
    el('option', { value: 'es', textContent: 'Español' }),
    el('option', { value: 'ru', textContent: 'Русский' }),
    el('option', { value: 'en', textContent: 'English' }));
  lang.value = data?.notifications?.language || 'es';
  const notes = el('textarea', { placeholder: 'Заметки: предпочтения, аллергии, прошлые визиты' });
  const consent = el('input', { type: 'checkbox', checked: true, id: 'nc-consent' });

  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field' }, el('label', {}, 'Имя'), name),
    el('div', { className: 'field' }, el('label', {}, 'Телефон'), phone),
    el('div', { className: 'field' }, el('label', {}, 'Язык сообщений'), lang),
    el('div', { className: 'field wide' }, el('label', {}, 'Заметки'), notes),
    el('div', { className: 'field wide' },
      el('label', { className: 'switch', htmlFor: 'nc-consent' },
        consent, el('span', { className: 'track', attrs: { 'aria-hidden': 'true' } }),
        el('span', { className: 'switch-text' },
          el('span', {}, 'Согласие на сообщения'),
          el('small', {}, 'Без него клиенту не уйдут подтверждения, напоминания и рассылки.'))))));

  const save = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Создать');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  save.onclick = async () => {
    if (name.value.trim().length < 2 || phone.value.replace(/\D/g, '').length < 7) {
      toast('warn', 'Проверьте данные', 'Нужны имя и корректный телефон.');
      return;
    }
    save.disabled = true;
    const res = await api(url('/api/admin/clients'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.value.trim(), phone: phone.value.trim(), lang: lang.value,
        notes: notes.value.trim(), consent: consent.checked,
      }),
    });
    const payload = await res.json().catch(() => ({}));
    if (res.ok) {
      d.close();
      toast('ok', 'Клиент добавлен', payload.client?.name || name.value.trim());
      renderClients(panel);
      return;
    }
    save.disabled = false;
    // Тот же телефон — тот же человек: открываем его карточку вместо дубля.
    if (res.status === 409 && payload.detail?.clientId) {
      d.close();
      toast('warn', 'Такой клиент уже есть', payload.detail.name || '');
      openClient({ id: payload.detail.clientId }, panel);
      return;
    }
    toast('err', 'Не создан',
      typeof payload.detail === 'string' ? payload.detail : 'Сервер отклонил запрос.');
  };
  d.footer.append(cancel, save);
}

async function openClient(client, panel) {
  const detail = await apiJson(url(`/api/admin/clients/${client.id}`));
  const d = drawer({ title: detail.name, subtitle: `${detail.phone} · ${detail.visits} визитов` });
  const notes = el('textarea', { value: detail.notes || '', placeholder: 'Заметки администратора' });
  const tags = el('input', { value: (detail.tags || []).join(', '), placeholder: 'VIP, окрашивание' });
  const consent = el('input', { type: 'checkbox', checked: detail.consent });
  const blocked = el('input', { type: 'checkbox', checked: detail.blocked });
  const points = el('input', { type: 'number', value: 0 });
  d.body.append(
    el('div', { className: 'block' }, el('h3', { className: 'section-title' }, 'Профиль'),
      el('div', { className: 'field' }, el('label', {}, 'Заметки'), notes),
      el('div', { className: 'field' }, el('label', {}, 'Теги через запятую'), tags),
      el('label', { className: 'switch' }, consent, el('span', { className: 'track' }), el('span', {}, 'Согласие на уведомления')),
      el('label', { className: 'switch' }, blocked, el('span', { className: 'track' }), el('span', {}, 'Чёрный список'))),
    el('div', { className: 'block' }, el('h3', { className: 'section-title' }, `Лояльность · ${detail.loyalty} баллов`),
      el('div', { className: 'field' }, el('label', {}, 'Начислить или списать'), points)),
    el('div', { className: 'block' }, el('h3', { className: 'section-title' }, 'История'),
      ...(detail.bookings || []).map((b) => el('p', { className: 'note' }, `${fmtDate(b.start)} · ${b.serviceId} · ${statusMeta(b.status).label} · ${money(b.paidAmount, b.currency)}`))),
  );
  const save = el('button', { className: 'btn btn-primary', textContent: 'Сохранить' });
  save.onclick = async () => {
    await apiJson(url(`/api/admin/clients/${detail.id}`), { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: notes.value, tags: tags.value.split(',').map((x) => x.trim()).filter(Boolean), consent: consent.checked, blocked: blocked.checked }) });
    if (Number(points.value)) await apiJson(url(`/api/admin/clients/${detail.id}/loyalty`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ points: Number(points.value), reason: 'Правка администратора' }) });
    d.close(); toast('ok', 'Карточка сохранена', detail.name); renderClients(panel);
  };
  d.footer.append(save);
}

async function renderWaitlist(panel) {
  const head = pageHead('Лист ожидания', 'Освободившиеся окна автоматически предлагаются подходящим клиентам.');
  const add = el('button', { className: 'btn btn-primary', textContent: 'Добавить клиента' });
  head.querySelector('.tools').append(add);
  const body = el('div', {}); panel.replaceChildren(head, body);
  const draw = async () => {
    const payload = await apiJson(url('/api/admin/waitlist?status=waiting'));
    const entries = payload.entries || [];
    body.replaceChildren(entries.length ? simpleTable(['Услуга', 'Мастер', 'Даты', 'Время', 'Статус'], entries.map((x) => [
      (data.services || []).find((s) => s.id === x.serviceId)?.title || x.serviceId,
      (data.masters || []).find((m) => m.id === x.masterId)?.name || 'любой',
      `${x.dateFrom} — ${x.dateTo}`, `${x.timeFrom || 'любое'} ${x.timeTo ? `— ${x.timeTo}` : ''}`, x.status,
    ])) : emptyState('clock', 'Лист ожидания пуст',
      'Добавьте клиента, которому подойдёт освободившееся окно.'));
  };
  add.onclick = () => {
    const d = drawer({ title: 'Добавить в лист ожидания', subtitle: 'Предложение уйдёт через очередь уведомлений' });
    const name = el('input', { placeholder: 'Имя' }), phone = el('input', { placeholder: '+598…' });
    const service = el('select', {}, ...(data.services || []).map((s) => el('option', { value: s.id, textContent: s.title })));
    const master = el('select', {}, el('option', { value: '', textContent: 'Любой мастер' }), ...(data.masters || []).map((m) => el('option', { value: m.id, textContent: m.name })));
    const from = el('input', { type: 'date' }), to = el('input', { type: 'date' });
    d.body.append(el('div', { className: 'grid' }, ...[['Имя', name], ['Телефон', phone], ['Услуга', service], ['Мастер', master], ['С', from], ['По', to]].map(([l, c]) => el('div', { className: 'field' }, el('label', {}, l), c))));
    const save = el('button', { className: 'btn btn-primary', textContent: 'Добавить' });
    save.onclick = async () => { await apiJson(url('/api/admin/waitlist'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.value, phone: phone.value, serviceId: service.value, masterId: master.value, dateFrom: from.value, dateTo: to.value }) }); d.close(); toast('ok', 'Клиент добавлен', 'Окно будет предложено автоматически.'); draw(); };
    d.footer.append(save);
  };
  await draw();
}

/* Рассылки. Отправка — единственное действие в панели, которое уходит наружу
   сразу и всем: отменить его нельзя, поэтому перед ним показываем, скольким
   именно людям уйдёт сообщение, и спрашиваем подтверждение. */

const SEGMENTS = [
  ['all', 'Все клиенты'],
  ['inactive', 'Не были 60+ дней'],
  ['first_time', 'Были один раз'],
  ['frequent', 'Частые'],
  ['no_show', 'С неявками'],
];
const SEGMENT_LABEL = Object.fromEntries(SEGMENTS);
const CAMPAIGN_STATUS = { draft: 'Черновик', sent: 'Отправлена' };

/** Сколько человек получит сообщение: те же правила, что и на сервере. */
async function segmentSize(segment) {
  const query = segment && segment !== 'all' ? `?segment=${encodeURIComponent(segment)}` : '';
  const rows = (await apiJson(url(`/api/admin/clients${query}`))).clients || [];
  return rows.filter((c) => c.consent && !c.blocked).length;
}

async function renderCampaigns(panel) {
  const head = pageHead('Рассылки', 'Сегменты, реактивация и ручные кампании с учётом согласия.');
  const body = el('div', {});
  const add = el('button', { className: 'btn btn-primary' }, icon('plus', { size: 15 }), 'Новая рассылка');
  head.querySelector('.tools').append(add);
  panel.replaceChildren(head, body);

  const draw = async () => {
    const rows = (await apiJson(url('/api/admin/campaigns'))).campaigns || [];
    body.replaceChildren(rows.length
      ? simpleTable(['Название', 'Сегмент', 'Статус', 'Получатели', ''], rows.map((c) => [
        c.name,
        SEGMENT_LABEL[c.segment] || c.segment,
        CAMPAIGN_STATUS[c.status] || c.status,
        String(c.recipients || 0),
        sendButton(c, draw),
      ]))
      : emptyState('send', 'Рассылок пока нет', 'Создайте сообщение для выбранного сегмента.'));
  };

  add.onclick = () => newCampaign(draw);
  await draw();
}

function sendButton(campaign, reload) {
  const sent = campaign.status === 'sent';
  const b = el('button', {
    className: sent ? 'btn btn-secondary btn-sm' : 'btn btn-primary btn-sm',
    textContent: sent ? 'Отправлена' : 'Отправить',
  });
  b.disabled = sent;
  b.onclick = async () => {
    b.disabled = true;
    let count = 0;
    try { count = await segmentSize(campaign.segment); } catch { /* спросим без числа */ }
    if (!count) {
      toast('warn', 'Некому отправлять',
        'В этом сегменте нет клиентов с согласием на сообщения.');
      b.disabled = false;
      return;
    }
    // Отменить отправленное нельзя: спрашиваем прямо, скольким людям это уйдёт.
    const yes = await confirmDialog({
      title: `Отправить ${count} клиентам?`,
      message: `«${campaign.name}» уйдёт сегменту «${SEGMENT_LABEL[campaign.segment] || campaign.segment}» `
        + 'через очередь уведомлений. Отменить отправку после подтверждения нельзя.',
      confirmLabel: 'Отправить',
      danger: true,
    });
    if (!yes) { b.disabled = false; return; }
    try {
      const res = await apiJson(url(`/api/admin/campaigns/${campaign.id}/send`), { method: 'POST' });
      toast('ok', 'Рассылка поставлена в очередь', `Получателей: ${res.queued}`);
    } catch (e) {
      toast('err', 'Не отправлено', e.message || 'Сервер отклонил запрос.');
    }
    reload();
  };
  return b;
}

function newCampaign(reload) {
  const d = drawer({ title: 'Новая рассылка', subtitle: 'Сохраняется черновиком — отправка отдельной кнопкой' });
  const name = el('input', { type: 'text', placeholder: 'Например: «Вернуть тех, кто давно не был»' });
  const segment = el('select', {}, ...SEGMENTS.map(([value, label]) =>
    el('option', { value, textContent: label })));
  const message = el('textarea', { placeholder: 'Текст сообщения клиенту' });
  const size = el('small', {}, 'Считаем получателей…');

  const refresh = async () => {
    try {
      const n = await segmentSize(segment.value);
      size.textContent = n
        ? `Получателей с согласием: ${n}`
        : 'В этом сегменте нет клиентов с согласием на сообщения.';
    } catch { size.textContent = 'Не удалось посчитать получателей.'; }
  };
  segment.onchange = refresh;

  d.body.append(el('div', { className: 'grid' },
    el('div', { className: 'field wide' }, el('label', {}, 'Название'), name),
    el('div', { className: 'field wide' }, el('label', {}, 'Сегмент'), segment, size),
    el('div', { className: 'field wide' }, el('label', {}, 'Сообщение'), message)));
  refresh();

  const save = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Сохранить черновик');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  save.onclick = async () => {
    if (name.value.trim().length < 2 || message.value.trim().length < 5) {
      toast('warn', 'Проверьте черновик', 'Нужны название и текст сообщения.');
      return;
    }
    save.disabled = true;
    try {
      await apiJson(url('/api/admin/campaigns'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.value.trim(), segment: segment.value,
                               message: message.value.trim() }),
      });
    } catch (e) {
      save.disabled = false;
      toast('err', 'Черновик не сохранён', e.message || 'Сервер отклонил запрос.');
      return;
    }
    d.close();
    toast('ok', 'Черновик сохранён', 'Отправка — кнопкой в списке.');
    reload();
  };
  d.footer.append(cancel, save);
}

async function renderFinance(panel) {
  const head = pageHead('Деньги и удержание', 'Ручной учёт оплат, выручка, комиссии и возвращаемость.');
  const body = el('div', {}); panel.replaceChildren(head, body); body.append(skeletonCards(4));
  try {
    const [f, r] = await Promise.all([apiJson(url('/api/admin/finance?days=30')), apiJson(url('/api/admin/retention'))]);
    const names = (obj, source, key) => Object.entries(obj || {}).map(([id, value]) => [source.find((x) => x.id === id)?.[key] || id, money(value, f.currency)]);
    // Визиты по абонементам — отдельной плиткой, а не внутри выручки: деньги за
    // них пришли в день продажи актива, и складывать одно с другим значило бы
    // посчитать их дважды. Но и прятать нельзя — мастер их отработал.
    const tiles = [['Выручка', money(f.revenue, f.currency)], ['Средний чек', money(f.averageCheck, f.currency)],
      ['Визиты', f.visits], ['Повторные', `${r.repeatRate}%`]];
    if (f.byAsset) tiles.splice(1, 0, ['По абонементам', money(f.byAsset, f.currency)]);
    const kpis = el('div', { className: 'kpis' },
      ...tiles.map(([label, value]) => el('div', { className: 'kpi' },
        el('span', { className: 'kpi-label' }, label), el('b', {}, String(value)))));
    const charts = el('div', { className: 'grid' },
      el('div', { className: 'card' }, el('h3', { className: 'section-title' }, 'По мастерам'),
        simpleTable(['Мастер', 'Выручка'], names(f.byMaster, data.masters || [], 'name'))),
      el('div', { className: 'card' }, el('h3', { className: 'section-title' }, 'Комиссии к выплате'),
        simpleTable(['Мастер', 'Сумма'], names(f.payroll, data.masters || [], 'name'))),
      el('div', { className: 'card' }, el('h3', { className: 'section-title' }, 'По услугам'),
        simpleTable(['Услуга', 'Выручка'], names(f.byService, data.services || [], 'title'))));
    body.replaceChildren(kpis, charts);
  } catch(e) { body.replaceChildren(errorState('Не удалось построить отчёт',e.message,()=>renderFinance(panel))); }
}

/* Платформа: филиалы, ресурсы, абонементы. Всё создаётся, правится и удаляется
   здесь же — иначе завести кресло можно, а переименовать его уже нет, и салон
   правит справочники через разработчика. Ссылки на людей и филиалы выбираются
   списком: идентификаторы руками не вводят. */

async function renderPlatform(panel) {
  const head = pageHead('Платформа', 'Филиалы, ресурсы, абонементы и сертификаты.');
  const body = el('div', {});
  panel.replaceChildren(head, body);
  body.append(skeletonTable(3, 4));

  let places = { locations: [], resources: [] };
  let assets = { assets: [] };
  let clients = [];
  try {
    [places, assets, clients] = await Promise.all([
      apiJson(url('/api/admin/locations')),
      apiJson(url('/api/admin/assets')),
      apiJson(url('/api/admin/clients')).then((r) => r.clients || []).catch(() => []),
    ]);
  } catch (e) {
    body.replaceChildren(errorState('Не удалось загрузить платформенные данные', e.message,
      () => renderPlatform(panel)));
    return;
  }

  const reload = () => renderPlatform(panel);
  const placeOptions = [['', 'Без филиала'],
    ...(places.locations || []).map((x) => [x.id, x.address ? `${x.name} — ${x.address}` : x.name])];
  const clientOptions = (clients || []).map((c) => [c.id, `${c.name || 'Без имени'} · ${c.phone}`]);
  const clientName = (id) => clients.find((c) => c.id === id)?.name || '—';
  const placeName = (id) => (places.locations || []).find((x) => x.id === id)?.name || '—';

  const LOCATION_FIELDS = [
    { key: 'code', label: 'Код', placeholder: 'centro' },
    { key: 'name', label: 'Название' },
    { key: 'address', label: 'Адрес' },
    { key: 'timezone', label: 'Часовой пояс', value: data.salon?.timezone || '' },
  ];
  const RESOURCE_FIELDS = [
    { key: 'code', label: 'Код', placeholder: 'chair-1' },
    { key: 'name', label: 'Название' },
    { key: 'kind', label: 'Тип', placeholder: 'chair' },
    { key: 'capacity', label: 'Вместимость', type: 'number', value: 1 },
    { key: 'locationId', label: 'Филиал', type: 'select', options: placeOptions },
  ];
  const ASSET_FIELDS = [
    { key: 'clientId', label: 'Клиент', type: 'select',
      options: clientOptions.length ? clientOptions : [['', 'Сначала заведите клиента']] },
    { key: 'kind', label: 'Тип', type: 'select',
      options: [['membership', 'Абонемент'], ['certificate', 'Сертификат']] },
    { key: 'code', label: 'Код' },
    { key: 'title', label: 'Название' },
    { key: 'balanceAmount', label: 'Баланс', type: 'number', value: 0 },
    { key: 'remainingUses', label: 'Осталось визитов', type: 'number', value: 0 },
  ];

  head.querySelector('.tools').append(
    addButton('Филиал', 'Новый филиал', LOCATION_FIELDS, '/api/admin/locations', reload),
    addButton('Ресурс', 'Новый ресурс', RESOURCE_FIELDS, '/api/admin/resources', reload),
    addButton('Абонемент / сертификат', 'Новый актив клиента', ASSET_FIELDS, '/api/admin/assets', reload));

  const card = (title, columns, rows) => el('div', { className: 'card' },
    el('h3', { className: 'section-title' }, title),
    rows.length ? simpleTable([...columns, ''], rows) : el('p', { className: 'hint' }, 'Пока пусто.'));

  body.replaceChildren(
    card('Филиалы', ['Код', 'Название', 'Адрес'], (places.locations || []).map((x) => [
      x.code, x.name, x.address || '—',
      platformRowActions({
        title: `филиал «${x.name}»`,
        fields: LOCATION_FIELDS.map((f) => ({ ...f, value: x[f.key] ?? '' })),
        endpoint: `/api/admin/locations/${x.id}`,
        removeText: `Филиал «${x.name}» будет удалён. Ресурсы останутся, но без адреса.`,
        reload,
      }),
    ])),
    card('Ресурсы', ['Код', 'Название', 'Тип', 'Вместимость', 'Филиал'],
      (places.resources || []).map((x) => [
        x.code, x.name, x.kind, String(x.capacity), placeName(x.locationId),
        platformRowActions({
          title: `ресурс «${x.name}»`,
          fields: RESOURCE_FIELDS.map((f) => ({ ...f, value: x[f.key] ?? (f.key === 'locationId' ? '' : '') })),
          endpoint: `/api/admin/resources/${x.id}`,
          removeText: `Ресурс «${x.name}» будет удалён.`,
          reload,
        }),
      ])),
    card('Абонементы и сертификаты', ['Клиент', 'Код', 'Название', 'Тип', 'Баланс / визиты'],
      (assets.assets || []).map((x) => [
        clientName(x.clientId), x.code, x.title,
        x.kind === 'membership' ? 'Абонемент' : 'Сертификат',
        `${x.balance} / ${x.uses}`,
        platformRowActions({
          title: `«${x.title}»`,
          // Тип после выдачи не меняем: сертификат и абонемент считаются по-разному.
          fields: ASSET_FIELDS.filter((f) => f.key !== 'kind')
            .map((f) => ({ ...f, value: x[{ balanceAmount: 'balance', remainingUses: 'uses' }[f.key] || f.key] ?? '' })),
          endpoint: `/api/admin/assets/${x.id}`,
          removeText: `«${x.title}» будет удалён вместе с остатком: ${x.balance} / ${x.uses}. `
            + 'Это списание оплаченного клиентом.',
          danger: true,
          reload,
        }),
      ])));
}

/** Кнопка «создать» в шапке раздела. */
function addButton(label, title, fields, endpoint, reload) {
  const button = el('button', { className: 'btn btn-secondary btn-sm' },
    icon('plus', { size: 14 }), label);
  button.onclick = () => platformForm({ title, fields, endpoint, method: 'POST', reload });
  return button;
}

/** «Изменить» и «Удалить» в строке справочника платформы. */
function platformRowActions({ title, fields, endpoint, removeText, danger = false, reload }) {
  const box = el('div', { className: 'row-actions' });
  const edit = el('button', { className: 'btn btn-secondary btn-sm', textContent: 'Изменить' });
  edit.onclick = () => platformForm({ title, fields, endpoint, method: 'PATCH', reload });
  const remove = el('button', {
    className: 'btn btn-ghost btn-sm', attrs: { 'aria-label': `Удалить: ${title}` },
  }, icon('trash', { size: 15 }));
  remove.onclick = async () => {
    const yes = await confirmDialog({
      title: `Удалить ${title}?`, message: removeText, confirmLabel: 'Удалить', danger: true,
    });
    if (!yes) return;
    const res = await api(url(endpoint), { method: 'DELETE' });
    const payload = await res.json().catch(() => ({}));
    if (res.ok) { toast('ok', 'Удалено', title); reload(); return; }
    // Отказ по связям — не сбой, а объяснение: показываем, что мешает.
    const detail = payload.detail;
    const reason = typeof detail === 'string' ? detail
      : [detail?.error, detail?.masters?.join(', '),
         detail?.bookings ? `записей: ${detail.bookings}` : ''].filter(Boolean).join(' — ');
    toast('err', 'Не удалено', reason || 'Сервер отклонил запрос.');
  };
  box.append(edit, remove);
  return box;
}

/** Одна форма и на создание, и на правку: поля те же, меняется только метод. */
function platformForm({ title, fields, endpoint, method, reload }) {
  // В диалоге удаления заголовок идёт после «Удалить», в шапке панели — сам по
  // себе: там же он и должен начинаться с большой буквы.
  const heading = title.charAt(0).toUpperCase() + title.slice(1);
  const d = drawer({ title: heading, subtitle: method === 'POST' ? 'Данные сохранятся внутри текущего бизнеса' : 'Правка справочника' });
  const controls = Object.fromEntries(fields.map((f) => {
    const control = f.type === 'select'
      ? el('select', {}, ...(f.options || []).map(([value, textContent]) =>
          el('option', { value, textContent })))
      : el('input', { type: f.type === 'number' ? 'number' : 'text', placeholder: f.placeholder || '' });
    control.value = f.value ?? '';
    return [f.key, control];
  }));
  d.body.append(el('div', { className: 'grid' }, ...fields.map((f) =>
    el('div', { className: 'field' }, el('label', {}, f.label), controls[f.key]))));

  const save = el('button', { className: 'btn btn-primary' }, icon('check', { size: 15 }), 'Сохранить');
  const cancel = el('button', { className: 'btn btn-ghost', textContent: 'Отмена' });
  cancel.onclick = d.close;
  save.onclick = async () => {
    save.disabled = true;
    const payload = Object.fromEntries(fields.map((f) => [f.key,
      f.type === 'number' ? Number(controls[f.key].value || 0) : controls[f.key].value]));
    const res = await api(url(endpoint), {
      method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) {
      save.disabled = false;
      toast('err', 'Не сохранено',
        typeof result.detail === 'string' ? result.detail : 'Проверьте поля.');
      return;
    }
    d.close();
    toast('ok', 'Сохранено', heading);
    // Новый или переименованный филиал нужен и форме мастера.
    if (endpoint.includes('/locations')) { await loadLocations(); redrawMasters(); }
    reload();
  };
  d.footer.append(cancel, save);
}

async function renderReviews(panel) {
  const head=pageHead('Отзывы','Оценки 1–4 остаются внутри, оценка 5 ведёт клиента в Google Maps.'); const body=el('div',{});panel.replaceChildren(head,body);
  // `public` и `private` — это про то, куда ушёл отзыв, и владельцу нужно
  // читать это словами: пятёрка ведёт клиента на карту, остальное остаётся у него.
  const REVIEW_STATUS = {
    requested: 'ждём ответа',
    public: 'ушёл в Google Maps',
    private: 'только для вас',
  };
  try {
    const rows = (await apiJson(url('/api/admin/reviews'))).reviews || [];
    body.replaceChildren(rows.length
      ? simpleTable(['Оценка', 'Комментарий', 'Что дальше'], rows.map((x) => [
        x.score ? `${x.score} / 5` : '—',
        x.feedback || '—',
        REVIEW_STATUS[x.status] || x.status,
      ]))
      : emptyState('checkCircle', 'Отзывов пока нет',
        'Просьба об оценке уходит через сутки после визита, отмеченного как «пришёл».'));
  } catch (e) {
    body.replaceChildren(errorState('Не удалось загрузить отзывы', e.message, () => renderReviews(panel)));
  }
}

function renderEnv(panel) {
  panel.replaceChildren(
    pageHead('.env', 'Переменные окружения для деплоя.'),
    el('div', { className: 'card' },
      el('p', { className: 'hint' },
        'Шпаргалка для деплоя: эти переменные задаются на сервере (Coolify → Environment Variables). '
        + 'Значения секретов здесь не показываются — они хранятся в окружении и в базе, а не в файлах репозитория.'),
      el('pre', { className: 'env', id: 'envBox', style: 'margin-top:16px' }, data.__env ?? '')));
}

/* ============================== НАВИГАЦИЯ =============================== */

/* Разделы сгруппированы по задачам администратора: сначала то, чем пользуются
   каждый день, потом справочники, интеграции и настройки. */
const NAV = [
  { title: 'Главная', items: [
    { id: '__schedule', label: 'Расписание', icon: 'calendar', lede: 'Занятость салона по дням' },
    { id: '__bookings', label: 'Записи', icon: 'list', lede: 'Все визиты клиентов' },
    { id: '__dialogs', label: 'Диалоги', icon: 'chat', lede: 'Переписка с ботом' },
    { id: '__stats', label: 'Статистика', icon: 'chart', lede: 'Записи, отмены, конверсия' },
  ] },
  { title: 'Управление', items: [
    { id: '__clients', label: 'Клиенты', icon: 'users', lede: 'Карточки, история и LTV' },
    { id: 'salon', label: 'Салон', icon: 'store' },
    { id: 'services', label: 'Услуги', icon: 'scissors' },
    { id: 'masters', label: 'Мастера', icon: 'users' },
    // График по датам — живой экран, а карточка мастера — справочник «как обычно».
    { id: '__shifts', label: 'График мастеров', icon: 'clock', lede: 'Отпуска, подмены и особые часы' },
    { id: '__waitlist', label: 'Лист ожидания', icon: 'clock', lede: 'Автозаполнение свободных окон' },
    { id: '__platform', label: 'Платформа', icon: 'store', lede: 'Филиалы, ресурсы и абонементы' },
  ] },
  // Подключения и ключи — раздел владельца. Администратор ведёт салон, а не
  // распоряжается доступами сервиса; сервер отвечает на его запросы 403, и
  // показывать раздел, который всё равно откажет, незачем.
  { title: 'Интеграции', owner: true, items: [
    // Google, Telegram, AI и Twilio живут здесь — на одном экране, а не
    // россыпью по панели. Отдельного раздела Google Calendar больше нет.
    { id: 'channel', label: 'Каналы связи', icon: 'send' },
    { id: '__database', label: 'База данных', icon: 'database', lede: 'Где хранятся записи и диалоги' },
  ] },
  { title: 'Автоматизация', items: [
    { id: 'ai', label: 'AI-диалог', icon: 'sparkles' },
    // Список людей и их роли ведёт владелец: администратор не заводит себе
    // равных, и сервер отвечает ему 403 на тот же запрос.
    { id: 'notificationsInternal', label: 'Внутренние уведомления', icon: 'users', owner: true },
    { id: 'notifications', label: 'Клиентские уведомления', icon: 'bell' },
    { id: '__notifications', label: 'Очередь уведомлений', icon: 'inbox', lede: 'Что отправлено и что не дошло' },
    { id: '__campaigns', label: 'Рассылки', icon: 'send', lede: 'Сегменты и реактивация' },
    { id: '__reviews', label: 'Отзывы', icon: 'checkCircle', lede: 'Оценки после визита' },
    { id: 'handoff', label: 'Передача администратору', icon: 'handoff' },
  ] },
  { title: 'Настройки', items: [
    { id: '__finance', label: 'Деньги и удержание', icon: 'chart', lede: 'Выручка, комиссии и LTV' },
    { id: 'policies', label: 'Правила и защита', icon: 'shield' },
    { id: '__billing', label: 'Тариф', icon: 'card' },
    { id: '__embed', label: 'Виджет', icon: 'code' },
    // Справка по переменным окружения — это про доступы сервера, не про салон.
    { id: '__env', label: '.env', icon: 'terminal', owner: true },
  ] },
];

const navItem = (id) => NAV.flatMap((g) => g.items).find((i) => i.id === id);
const LIVE = {
  __bookings: renderBookings, __schedule: renderSchedule, __shifts: renderShifts,
  __clients: renderClients, __waitlist: renderWaitlist, __campaigns: renderCampaigns,
  __finance: renderFinance, __platform: renderPlatform, __reviews: renderReviews,
  __dialogs: renderConversations,
  __notifications: renderNotificationQueue,
  __stats: renderStats, __billing: renderBilling, __embed: renderEmbed,
  __database: renderDatabase,
};

function pageHead(title, lede) {
  return el('div', { className: 'page-head' },
    el('div', { className: 'titles' },
      el('h1', {}, title),
      lede ? el('p', { className: 'lede' }, lede) : null),
    el('div', { className: 'tools' }));
}

function renderAll() {
  const nav = $('#nav');
  const host = $('#panels');
  nav.replaceChildren();
  host.replaceChildren();

  NAV.forEach((group) => {
    if (group.owner && !isOwner()) return;
    const box = el('div', { className: 'nav-group' }, el('h3', {}, group.title));
    group.items.forEach((item) => {
      if (item.owner && !isOwner()) return;
      // Раздел схемы может отсутствовать (схема — источник правды, не этот список).
      const section = schema.sections.find((s) => s.id === item.id);
      if (!item.id.startsWith('__') && !section) return;
      const btn = el('button', {
        className: 'nav-item', type: 'button', dataset: { id: item.id },
        attrs: { 'aria-current': 'false' },
      }, icon(item.icon, { size: 17 }), el('span', {}, item.label));
      btn.onclick = () => { selectPanel(item.id); closeSidebar(); };
      box.append(btn);

      host.append(el('section', { className: 'panel', dataset: { panel: item.id } }));
    });
    if (box.children.length > 1) nav.append(box);
  });

  selectPanel(active && navItem(active) ? active : '__schedule');
}

function selectPanel(id, { force = false } = {}) {
  if (!navItem(id)) id = '__schedule';
  const same = active === id;
  active = id;

  document.querySelectorAll('.nav-item').forEach((b) => {
    const on = b.dataset.id === id;
    b.setAttribute('aria-current', on ? 'page' : 'false');
  });
  document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === id));

  const meta = navItem(id);
  $('#pageTitle').textContent = meta.label;
  $('#pageLede').textContent = meta.lede ?? '';

  const panel = document.querySelector(`.panel[data-panel="${id}"]`);
  if (!panel) return;
  // Живые разделы перезагружаются при каждом входе: данные меняются на сервере.
  if (LIVE[id]) {
    if (!same || force || !panel.children.length) LIVE[id](panel);
    return;
  }
  if (id === '__env') { renderEnv(panel); return; }
  if (panel.children.length) return;   // форма настроек строится один раз

  const section = schema.sections.find((s) => s.id === id);
  const card = el('div', { className: 'card' });
  if (section.hint) card.append(el('p', { className: 'hint', style: 'margin-bottom:20px' }, section.hint));
  // «Каналы связи» — единственный экран, где настраиваются чужие сервисы:
  // календарь, бот, модель, отправка сообщений. В остальных разделах остаётся
  // поведение бота, а не доступы, — искать ключи по всей панели больше не нужно.
  if (id === 'channel') {
    card.append(
      subSection('Google Calendar', 'Записи попадают в календарь мастера.',
                 googleConnectBlock(), sectionFields('integration')),
      subSection('Telegram', 'Бот салона: уведомления своим и передача администратору.',
                 telegramConnectBlock()),
      subSection('AI-диалог', 'Провайдер и модель. Тон и правила — на экране «AI-диалог».',
                 aiConnectBlock()),
      subSection('Сообщения клиентам', 'Чем отправляем подтверждения и напоминания.',
                 twilioConnectBlock(), sectionFields('notificationsTwilio')),
      subSection('Канал диалога', 'Где бот разговаривает с клиентом. Это не то же самое, '
                 + 'что канал уведомлений выше.', renderObjectSection(section)),
    );
  }
  else if (id === 'notificationsInternal') card.append(staffBlock(), renderObjectSection(section));
  // Ключ провайдера переехал на «Каналы связи»; здесь остаётся поведение —
  // тон, язык, число шагов.
  else if (id === 'ai') card.append(renderObjectSection(section));
  else if (section.kind === 'list') card.append(renderListSection(section));
  else card.append(renderObjectSection(section));
  panel.replaceChildren(pageHead(meta.label, ''), card);
}

/* ============================== ШАПКА ================================== */

function renderTenantPicker() {
  const t = current();
  $('#tenantName').textContent = t?.title ?? tenant;
  $('#tenantCode').textContent = t?.slug ?? '';
  $('#brandName').textContent = t?.title ?? 'Demo Salon';
  $('#brandLogo').textContent = (t?.title ?? 'A').trim().charAt(0).toUpperCase();

  $('#tenantMenu').replaceChildren(
    ...tenants.map((item) => {
      const b = el('button', {
        className: 'menu-item', type: 'button',
        attrs: { role: 'menuitem', 'aria-current': String(item.slug === tenant) },
      }, el('span', {}, item.title),
         el('span', { className: 'meta' }, `${item.services} усл. · ${item.masters} маст.`));
      b.onclick = () => { closeMenus(); switchTenant(item.slug); };
      return b;
    }),
    el('div', { className: 'menu-sep' }),
    menuAction('Новый бизнес', createTenant, { icon: 'plus' }),
    menuAction('Удалить текущий', deleteTenant, { icon: 'trash', danger: true, disabled: tenants.length < 2 }),
  );
}

function menuAction(label, handler, { danger = false, disabled = false, icon: name = null } = {}) {
  const b = el('button', {
    className: `menu-item${danger ? ' danger' : ''}`, type: 'button', disabled,
    attrs: { role: 'menuitem' },
  }, name ? icon(name, { size: 15 }) : null, el('span', {}, label));
  b.onclick = () => { closeMenus(); handler(); };
  return b;
}

function renderProfileMenu() {
  $('#profileMenu').replaceChildren(
    menuAction('Обновить данные', () => load(), { icon: 'refresh' }),
    menuAction('Открыть демо-виджет', () => window.open(url('/demo.html'), '_blank'), { icon: 'external' }),
    el('div', { className: 'menu-sep' }),
    menuAction('Сменить пароль', () => askPasswordChange(), { icon: 'refresh' }),
    menuAction('Двухфакторный вход', () => askTotp(), { icon: 'external' }),
    el('div', { className: 'menu-sep' }),
    menuAction('Выйти', () => logout(), { icon: 'logout', danger: true }),
  );
}

/** Состояние интеграций: видно с одного взгляда, что настроено. */
function renderStatuses(info) {
  const t = current();
  const calendar = info?.calendarMode ?? t?.calendarMode;
  const ai = info?.aiEnabled ?? t?.aiEnabled;
  const badges = [
    calendar === 'google'
      ? { text: 'Календарь', cls: 'ok', icon: 'checkCircle' }
      : { text: 'Календарь: демо', cls: 'warn', icon: 'warning' },
    ai ? { text: 'AI-диалог', cls: 'ok', icon: 'sparkles' }
       : { text: 'AI выключен', cls: 'off', icon: 'sparkles' },
    (data?.channel?.kind ?? 'web') === 'whatsapp'
      ? { text: 'WhatsApp', cls: 'ok', icon: 'send' }
      : { text: 'Веб-виджет', cls: 'off', icon: 'code' },
  ];
  $('#statuses').replaceChildren(...badges.map((b) => el('span', { className: `status-badge ${b.cls}` },
    icon(b.icon, { size: 13 }), b.text)));
}

const closeMenus = () => {
  document.querySelectorAll('.menu.open').forEach((m) => m.classList.remove('open'));
  document.querySelectorAll('[aria-haspopup="menu"]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
};

function toggleMenu(btnId, menuId) {
  const menu = $(menuId);
  const wasOpen = menu.classList.contains('open');
  closeMenus();
  menu.classList.toggle('open', !wasOpen);
  $(btnId).setAttribute('aria-expanded', String(!wasOpen));
}

const closeSidebar = () => {
  $('#sidebar').classList.remove('open');
  $('#navScrim').classList.remove('in');
  setTimeout(() => { $('#navScrim').hidden = true; }, 220);
  $('#burger').setAttribute('aria-expanded', 'false');
};

function openSidebar() {
  $('#sidebar').classList.add('open');
  $('#navScrim').hidden = false;
  requestAnimationFrame(() => $('#navScrim').classList.add('in'));
  $('#burger').setAttribute('aria-expanded', 'true');
  $('#sidebar').querySelector('.nav-item')?.focus();
}

/* ============================== БИЗНЕСЫ ================================ */

async function switchTenant(slug) {
  if (dirty) {
    const ok = await confirmDialog({
      title: 'Есть несохранённые правки',
      message: 'Переключение на другой бизнес отбросит их. Сохранить сейчас?',
      confirmLabel: 'Переключить без сохранения', danger: true,
    });
    if (!ok) return;
  }
  tenant = slug;
  googleStatus = null;
  googleCalendars = [];
  masterTgState = null;   // ссылки и чаты — свои у каждого бизнеса
  const params = new URLSearchParams(location.search);
  params.set('tenant', slug);
  history.replaceState(null, '', `${location.pathname}?${params}`);
  active = null;
  await load();
}

async function createTenant() {
  const title = await promptDialog({
    title: 'Новый бизнес', label: 'Название', placeholder: 'Second Demo',
    message: 'Салон получит собственные услуги, мастеров и код виджета.',
  });
  if (!title) return;
  const suggested = title.toLowerCase().trim()
    .replace(/[^a-zа-я0-9]+/gi, '-').replace(/^-|-$/g, '').slice(0, 30);
  const slug = await promptDialog({
    title: 'Код бизнеса', label: 'Латиница, цифры и дефис', value: suggested,
    message: 'Код попадёт в тег виджета и в адреса API — потом его не поменять.',
    confirmLabel: 'Создать',
  });
  if (!slug) return;
  const copyFrom = await confirmDialog({
    title: 'Скопировать справочники?',
    message: `Услуги и мастера будут перенесены из «${current()?.title ?? tenant}». `
      + 'Ключи, календари и секреты не копируются.',
    confirmLabel: 'Скопировать', cancelLabel: 'Создать пустым',
  });

  const res = await api('/api/admin/tenants', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug, title, copyFrom: copyFrom ? tenant : null }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) { toast('err', 'Бизнес не создан', body.detail ?? 'Сервер отклонил запрос.'); return; }
  tenants = body.tenants;
  await switchTenant(body.tenant);
  toast('ok', `Бизнес «${title}» создан`, 'Заполните адрес, услуги и мастеров.');
}

async function deleteTenant() {
  const t = current();
  if (!t) return;
  const ok = await confirmDialog({
    title: `Удалить бизнес «${t.title}»?`,
    message: 'Настройки, услуги и мастера будут удалены безвозвратно. Записи в базе останутся, '
      + 'но виджет этого салона перестанет работать.',
    confirmLabel: 'Удалить бизнес', danger: true,
  });
  if (!ok) return;
  const res = await api(`/api/admin/tenants/${encodeURIComponent(tenant)}`, { method: 'DELETE' });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) { toast('err', 'Не удалось удалить', body.detail ?? 'Сервер отклонил запрос.'); return; }
  tenants = body.tenants;
  dirty = false;
  toast('ok', `Бизнес «${t.title}» удалён`, '');
  await switchTenant(tenants[0].slug);
}

/* ============================== ЗАГРУЗКА =============================== */

function updateEnvBox() {
  const box = $('#envBox');
  if (box) box.textContent = data.__env ?? '';
}

function updateRuntimeBadges(info) {
  const t = current();
  if (t) { t.calendarMode = info.calendarMode; t.aiEnabled = info.aiEnabled; }
  renderStatuses(info);
}

function showErrors(list) {
  const box = $('#errors');
  if (!list?.length) {
    box.className = 'errors';
    box.replaceChildren();
    document.querySelectorAll('.nav-item .dot').forEach((d) => d.remove());
    return;
  }
  box.className = 'errors on';
  box.replaceChildren(
    el('strong', {}, 'Не сохранено — исправьте:'),
    el('ul', {}, ...list.map((e) => el('li', {}, String(e)))),
  );
  // Подсветим разделы, к которым относятся ошибки.
  const titles = new Map(schema.sections.map((s) => [s.title, s.id]));
  const guilty = new Set();
  list.forEach((e) => {
    for (const [title, id] of titles) if (String(e).startsWith(title)) guilty.add(id);
  });
  document.querySelectorAll('.nav-item').forEach((b) => {
    b.querySelector('.dot')?.remove();
    if (guilty.has(b.dataset.id)) {
      b.append(el('span', { className: 'dot', attrs: { role: 'img', 'aria-label': 'есть ошибки' } }));
    }
  });
}

async function load() {
  // Роль читаем до отрисовки навигации: иначе администратор на мгновение видит
  // разделы владельца, а затем они пропадают.
  try { me = await apiJson('/api/admin/auth/state'); } catch { me = { role: '' }; }

  const list = await apiJson('/api/admin/tenants');
  tenants = list.tenants;
  if (!tenants.length) { status('error', 'Нет ни одного бизнеса'); return; }
  if (!tenants.some((t) => t.slug === tenant)) tenant = tenants[0].slug;
  renderTenantPicker();
  renderProfileMenu();

  const [s, c] = await Promise.all([
    apiJson('/api/admin/schema'),
    apiJson(url('/api/admin/config')),
  ]);
  schema = s.schema;
  data = c.data;
  data.__env = c.env;
  updateRuntimeBadges(c);
  showErrors([]);
  renderAll();
  if (c.calendarMode === 'google') await loadCalendars();
  await loadLocations();
  status('saved', 'Автосохранение включено');
}

/* ============================== СОБЫТИЯ ================================ */

function wireChrome() {
  $('#burger').append(icon('menu', { size: 20 }));
  $('#profileBtn').append(icon('user', { size: 18 }));

  $('#burger').onclick = (e) => {
    e.stopPropagation();
    if ($('#sidebar').classList.contains('open')) closeSidebar(); else openSidebar();
  };
  $('#navScrim').onclick = closeSidebar;
  $('#saveNow').onclick = () => save({ immediate: true });
  $('#tenantBtn').onclick = (e) => { e.stopPropagation(); toggleMenu('#tenantBtn', '#tenantMenu'); };
  $('#profileBtn').onclick = (e) => { e.stopPropagation(); toggleMenu('#profileBtn', '#profileMenu'); };

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu')) closeMenus();
    if (!e.target.closest('.sidebar, #burger')) closeSidebar();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeMenus(); closeSidebar(); }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      save({ immediate: true });
    }
  });
  window.addEventListener('beforeunload', (e) => { if (dirty) e.preventDefault(); });
}

async function boot() {
  $('#shell').hidden = false;
  try {
    await load();
  } catch (e) {
    if (String(e.message).includes('вход') || String(e.message).includes('отключена')) return;  // экран входа уже показан
    status('error', 'Сервер недоступен');
    toast('err', 'Не удалось загрузить панель', 'Проверьте, что сервис запущен.');
  }
}

wireChrome();
// Пробуем загрузиться как есть: сессия могла остаться в cookie, а на локальной
// машине админка бывает открыта (ADMIN_ALLOW_NO_TOKEN=1). Форму входа показываем
// только при отказе сервера.
boot();
