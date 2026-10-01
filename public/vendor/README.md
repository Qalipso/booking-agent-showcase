# Сторонние библиотеки

Лежат в репозитории, а не подключаются с CDN: панель салона должна открываться,
даже если внешняя сеть недоступна, и не должна зависеть от чужого аптайма.

| Файл | Библиотека | Версия | Лицензия |
| --- | --- | --- | --- |
| `shoelace/shoelace.js` | [Shoelace](https://shoelace.style) © Cory LaViska | 2.20.1 | MIT |
| `shoelace/light.css` | Shoelace, светлая тема | 2.20.1 | MIT |
| `chart.umd.min.js` | [Chart.js](https://www.chartjs.org) | 4.4.7 | MIT |
| `flatpickr.min.js`, `flatpickr.min.css`, `flatpickr.ru.js` | [flatpickr](https://flatpickr.js.org) | 4.6.13 | MIT |
| `motion.min.js` | [Motion](https://motion.dev) | 13.1.1 | MIT |

Иконки — контуры [Lucide](https://lucide.dev) (ISC), вставленные инлайном в
`public/admin/ui.js`: два десятка глифов не стоят подключения библиотеки.

## Как пересобрать Shoelace

`shoelace.js` — не дистрибутив целиком, а сборка из семи компонентов, которые
реально нужны форме настроек. Полный пакет весит в разы больше.

```bash
npm i --no-save @shoelace-style/shoelace@2.20.1 esbuild
```

Файл входа:

```js
import '@shoelace-style/shoelace/dist/components/input/input.js';
import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
import '@shoelace-style/shoelace/dist/components/select/select.js';
import '@shoelace-style/shoelace/dist/components/option/option.js';
import '@shoelace-style/shoelace/dist/components/switch/switch.js';
import '@shoelace-style/shoelace/dist/components/checkbox/checkbox.js';
import '@shoelace-style/shoelace/dist/components/tooltip/tooltip.js';
```

```bash
npx esbuild entry.js --bundle --format=esm --minify --target=es2020 --outfile=shoelace.js
```

Системные значки Shoelace вшиты в бандл, поэтому `setBasePath` не нужен и за
иконками в сеть компонент не ходит — это проверяется списком сетевых запросов
панели: все адреса должны быть локальными.

Палитра задаётся не здесь: `light.css` подключается как есть, а поверх идёт
`public/admin/shoelace-theme.css`, где переменные `--sl-*` связаны с токенами
бренда. Правка цвета — в `public/admin/tokens.css`.

## Как пересобрать Motion

`motion.min.js` — не дистрибутив целиком, а сборка из шести функций, которые
реально нужны панели. Полный `dist/motion.js` вдвое больше, а react-обёртки и
слои совместимости здесь не используются вовсе.

```bash
npm i --no-save motion@13.1.1 esbuild
```

Файл входа:

```js
export { animate, inView, stagger, spring, hover, press } from 'motion';
```

```bash
npx esbuild entry.js --bundle --format=iife --global-name=Motion \
  --minify --target=es2020 --outfile=motion.min.js
```

Глобальное имя обязано остаться `Motion`: панель подключает библиотеку обычным
`<script>`, как Chart.js и flatpickr, и берёт `window.Motion`. Анимации всюду
необязательны — при `prefers-reduced-motion` и при отсутствии библиотеки экран
просто рисуется без движения.
