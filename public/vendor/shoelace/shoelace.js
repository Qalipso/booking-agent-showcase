var f=(t,e,o)=>()=>{if(o)throw o[0];try{return t&&(e=t(t=0)),e}catch(i){throw o=[i],i}};var Hs=(t,e)=>()=>{try{return e||t((e={exports:{}}).exports,e),e.exports}catch(o){throw e=0,o}};var Qe,to,ko,_i,Se,wi,z,xi,$o,So=f(()=>{Qe=globalThis,to=Qe.ShadowRoot&&(Qe.ShadyCSS===void 0||Qe.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,ko=Symbol(),_i=new WeakMap,Se=class{constructor(e,o,i){if(this._$cssResult$=!0,i!==ko)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=o}get styleSheet(){let e=this.o,o=this.t;if(to&&e===void 0){let i=o!==void 0&&o.length===1;i&&(e=_i.get(o)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),i&&_i.set(o,e))}return e}toString(){return this.cssText}},wi=t=>new Se(typeof t=="string"?t:t+"",void 0,ko),z=(t,...e)=>{let o=t.length===1?t[0]:e.reduce((i,r,s)=>i+(l=>{if(l._$cssResult$===!0)return l.cssText;if(typeof l=="number")return l;throw Error("Value passed to 'css' function must be a 'css' function result: "+l+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+t[s+1],t[0]);return new Se(o,t,ko)},xi=(t,e)=>{if(to)t.adoptedStyleSheets=e.map(o=>o instanceof CSSStyleSheet?o:o.styleSheet);else for(let o of e){let i=document.createElement("style"),r=Qe.litNonce;r!==void 0&&i.setAttribute("nonce",r),i.textContent=o.cssText,t.appendChild(i)}},$o=to?t=>t:t=>t instanceof CSSStyleSheet?(e=>{let o="";for(let i of e.cssRules)o+=i.cssText;return wi(o)})(t):t});var Ns,Us,qs,js,Ws,Ks,Vt,Ci,Xs,Ys,Ae,Dt,eo,ki,Et,Ee=f(()=>{So();So();({is:Ns,defineProperty:Us,getOwnPropertyDescriptor:qs,getOwnPropertyNames:js,getOwnPropertySymbols:Ws,getPrototypeOf:Ks}=Object),Vt=globalThis,Ci=Vt.trustedTypes,Xs=Ci?Ci.emptyScript:"",Ys=Vt.reactiveElementPolyfillSupport,Ae=(t,e)=>t,Dt={toAttribute(t,e){switch(e){case Boolean:t=t?Xs:null;break;case Object:case Array:t=t==null?t:JSON.stringify(t)}return t},fromAttribute(t,e){let o=t;switch(e){case Boolean:o=t!==null;break;case Number:o=t===null?null:Number(t);break;case Object:case Array:try{o=JSON.parse(t)}catch{o=null}}return o}},eo=(t,e)=>!Ns(t,e),ki={attribute:!0,type:String,converter:Dt,reflect:!1,useDefault:!1,hasChanged:eo};Symbol.metadata??(Symbol.metadata=Symbol("metadata")),Vt.litPropertyMetadata??(Vt.litPropertyMetadata=new WeakMap);Et=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??(this.l=[])).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,o=ki){if(o.state&&(o.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((o=Object.create(o)).wrapped=!0),this.elementProperties.set(e,o),!o.noAccessor){let i=Symbol(),r=this.getPropertyDescriptor(e,i,o);r!==void 0&&Us(this.prototype,e,r)}}static getPropertyDescriptor(e,o,i){let{get:r,set:s}=qs(this.prototype,e)??{get(){return this[o]},set(l){this[o]=l}};return{get:r,set(l){let h=r?.call(this);s?.call(this,l),this.requestUpdate(e,h,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??ki}static _$Ei(){if(this.hasOwnProperty(Ae("elementProperties")))return;let e=Ks(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(Ae("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(Ae("properties"))){let o=this.properties,i=[...js(o),...Ws(o)];for(let r of i)this.createProperty(r,o[r])}let e=this[Symbol.metadata];if(e!==null){let o=litPropertyMetadata.get(e);if(o!==void 0)for(let[i,r]of o)this.elementProperties.set(i,r)}this._$Eh=new Map;for(let[o,i]of this.elementProperties){let r=this._$Eu(o,i);r!==void 0&&this._$Eh.set(r,o)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let o=[];if(Array.isArray(e)){let i=new Set(e.flat(1/0).reverse());for(let r of i)o.unshift($o(r))}else e!==void 0&&o.push($o(e));return o}static _$Eu(e,o){let i=o.attribute;return i===!1?void 0:typeof i=="string"?i:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??(this._$EO=new Set)).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,o=this.constructor.elementProperties;for(let i of o.keys())this.hasOwnProperty(i)&&(e.set(i,this[i]),delete this[i]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return xi(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??(this.renderRoot=this.createRenderRoot()),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,o,i){this._$AK(e,i)}_$ET(e,o){let i=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,i);if(r!==void 0&&i.reflect===!0){let s=(i.converter?.toAttribute!==void 0?i.converter:Dt).toAttribute(o,i.type);this._$Em=e,s==null?this.removeAttribute(r):this.setAttribute(r,s),this._$Em=null}}_$AK(e,o){let i=this.constructor,r=i._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let s=i.getPropertyOptions(r),l=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:Dt;this._$Em=r;let h=l.fromAttribute(o,s.type);this[r]=h??this._$Ej?.get(r)??h,this._$Em=null}}requestUpdate(e,o,i,r=!1,s){if(e!==void 0){let l=this.constructor;if(r===!1&&(s=this[e]),i??(i=l.getPropertyOptions(e)),!((i.hasChanged??eo)(s,o)||i.useDefault&&i.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(l._$Eu(e,i))))return;this.C(e,o,i)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,o,{useDefault:i,reflect:r,wrapped:s},l){i&&!(this._$Ej??(this._$Ej=new Map)).has(e)&&(this._$Ej.set(e,l??o??this[e]),s!==!0||l!==void 0)||(this._$AL.has(e)||(this.hasUpdated||i||(o=void 0),this._$AL.set(e,o)),r===!0&&this._$Em!==e&&(this._$Eq??(this._$Eq=new Set)).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(o){Promise.reject(o)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??(this.renderRoot=this.createRenderRoot()),this._$Ep){for(let[r,s]of this._$Ep)this[r]=s;this._$Ep=void 0}let i=this.constructor.elementProperties;if(i.size>0)for(let[r,s]of i){let{wrapped:l}=s,h=this[r];l!==!0||this._$AL.has(r)||h===void 0||this.C(r,void 0,s,h)}}let e=!1,o=this._$AL;try{e=this.shouldUpdate(o),e?(this.willUpdate(o),this._$EO?.forEach(i=>i.hostUpdate?.()),this.update(o)):this._$EM()}catch(i){throw e=!1,this._$EM(),i}e&&this._$AE(o)}willUpdate(e){}_$AE(e){this._$EO?.forEach(o=>o.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&(this._$Eq=this._$Eq.forEach(o=>this._$ET(o,this[o]))),this._$EM()}updated(e){}firstUpdated(e){}};Et.elementStyles=[],Et.shadowRootOptions={mode:"open"},Et[Ae("elementProperties")]=new Map,Et[Ae("finalized")]=new Map,Ys?.({ReactiveElement:Et}),(Vt.reactiveElementVersions??(Vt.reactiveElementVersions=[])).push("2.1.2")});function Di(t,e){if(!Oo(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return Si!==void 0?Si.createHTML(e):e}function Yt(t,e,o=t,i){if(e===X)return e;let r=i!==void 0?o._$Co?.[i]:o._$Cl,s=Pe(e)?void 0:e._$litDirective$;return r?.constructor!==s&&(r?._$AO?.(!1),s===void 0?r=void 0:(r=new s(t),r._$AT(t,o,i)),i!==void 0?(o._$Co??(o._$Co=[]))[i]=r:o._$Cl=r),r!==void 0&&(e=Yt(t,r._$AS(t,e.values),r,i)),e}var Oe,$i,oo,Si,Eo,zt,zo,Gs,Xt,Te,Pe,Oo,Pi,Ao,ze,Ai,Ei,Wt,zi,Oi,Li,To,x,Ri,Vi,X,V,Ti,Kt,Mi,Le,io,re,Gt,ro,so,lo,no,Bi,Zs,Ii,bt=f(()=>{Oe=globalThis,$i=t=>t,oo=Oe.trustedTypes,Si=oo?oo.createPolicy("lit-html",{createHTML:t=>t}):void 0,Eo="$lit$",zt=`lit$${Math.random().toFixed(9).slice(2)}$`,zo="?"+zt,Gs=`<${zo}>`,Xt=document,Te=()=>Xt.createComment(""),Pe=t=>t===null||typeof t!="object"&&typeof t!="function",Oo=Array.isArray,Pi=t=>Oo(t)||typeof t?.[Symbol.iterator]=="function",Ao=`[ 	
\f\r]`,ze=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ai=/-->/g,Ei=/>/g,Wt=RegExp(`>|${Ao}(?:([^\\s"'>=/]+)(${Ao}*=${Ao}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),zi=/'/g,Oi=/"/g,Li=/^(?:script|style|textarea|title)$/i,To=t=>(e,...o)=>({_$litType$:t,strings:e,values:o}),x=To(1),Ri=To(2),Vi=To(3),X=Symbol.for("lit-noChange"),V=Symbol.for("lit-nothing"),Ti=new WeakMap,Kt=Xt.createTreeWalker(Xt,129);Mi=(t,e)=>{let o=t.length-1,i=[],r,s=e===2?"<svg>":e===3?"<math>":"",l=ze;for(let h=0;h<o;h++){let c=t[h],p,u,d=-1,g=0;for(;g<c.length&&(l.lastIndex=g,u=l.exec(c),u!==null);)g=l.lastIndex,l===ze?u[1]==="!--"?l=Ai:u[1]!==void 0?l=Ei:u[2]!==void 0?(Li.test(u[2])&&(r=RegExp("</"+u[2],"g")),l=Wt):u[3]!==void 0&&(l=Wt):l===Wt?u[0]===">"?(l=r??ze,d=-1):u[1]===void 0?d=-2:(d=l.lastIndex-u[2].length,p=u[1],l=u[3]===void 0?Wt:u[3]==='"'?Oi:zi):l===Oi||l===zi?l=Wt:l===Ai||l===Ei?l=ze:(l=Wt,r=void 0);let m=l===Wt&&t[h+1].startsWith("/>")?" ":"";s+=l===ze?c+Gs:d>=0?(i.push(p),c.slice(0,d)+Eo+c.slice(d)+zt+m):c+zt+(d===-2?h:m)}return[Di(t,s+(t[o]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),i]},Le=class t{constructor({strings:e,_$litType$:o},i){let r;this.parts=[];let s=0,l=0,h=e.length-1,c=this.parts,[p,u]=Mi(e,o);if(this.el=t.createElement(p,i),Kt.currentNode=this.el.content,o===2||o===3){let d=this.el.content.firstChild;d.replaceWith(...d.childNodes)}for(;(r=Kt.nextNode())!==null&&c.length<h;){if(r.nodeType===1){if(r.hasAttributes())for(let d of r.getAttributeNames())if(d.endsWith(Eo)){let g=u[l++],m=r.getAttribute(d).split(zt),v=/([.?@])?(.*)/.exec(g);c.push({type:1,index:s,name:v[2],strings:m,ctor:v[1]==="."?ro:v[1]==="?"?so:v[1]==="@"?lo:Gt}),r.removeAttribute(d)}else d.startsWith(zt)&&(c.push({type:6,index:s}),r.removeAttribute(d));if(Li.test(r.tagName)){let d=r.textContent.split(zt),g=d.length-1;if(g>0){r.textContent=oo?oo.emptyScript:"";for(let m=0;m<g;m++)r.append(d[m],Te()),Kt.nextNode(),c.push({type:2,index:++s});r.append(d[g],Te())}}}else if(r.nodeType===8)if(r.data===zo)c.push({type:2,index:s});else{let d=-1;for(;(d=r.data.indexOf(zt,d+1))!==-1;)c.push({type:7,index:s}),d+=zt.length-1}s++}}static createElement(e,o){let i=Xt.createElement("template");return i.innerHTML=e,i}};io=class{constructor(e,o){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=o}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:o},parts:i}=this._$AD,r=(e?.creationScope??Xt).importNode(o,!0);Kt.currentNode=r;let s=Kt.nextNode(),l=0,h=0,c=i[0];for(;c!==void 0;){if(l===c.index){let p;c.type===2?p=new re(s,s.nextSibling,this,e):c.type===1?p=new c.ctor(s,c.name,c.strings,this,e):c.type===6&&(p=new no(s,this,e)),this._$AV.push(p),c=i[++h]}l!==c?.index&&(s=Kt.nextNode(),l++)}return Kt.currentNode=Xt,r}p(e){let o=0;for(let i of this._$AV)i!==void 0&&(i.strings!==void 0?(i._$AI(e,i,o),o+=i.strings.length-2):i._$AI(e[o])),o++}},re=class t{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,o,i,r){this.type=2,this._$AH=V,this._$AN=void 0,this._$AA=e,this._$AB=o,this._$AM=i,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,o=this._$AM;return o!==void 0&&e?.nodeType===11&&(e=o.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,o=this){e=Yt(this,e,o),Pe(e)?e===V||e==null||e===""?(this._$AH!==V&&this._$AR(),this._$AH=V):e!==this._$AH&&e!==X&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Pi(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==V&&Pe(this._$AH)?this._$AA.nextSibling.data=e:this.T(Xt.createTextNode(e)),this._$AH=e}$(e){let{values:o,_$litType$:i}=e,r=typeof i=="number"?this._$AC(e):(i.el===void 0&&(i.el=Le.createElement(Di(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===r)this._$AH.p(o);else{let s=new io(r,this),l=s.u(this.options);s.p(o),this.T(l),this._$AH=s}}_$AC(e){let o=Ti.get(e.strings);return o===void 0&&Ti.set(e.strings,o=new Le(e)),o}k(e){Oo(this._$AH)||(this._$AH=[],this._$AR());let o=this._$AH,i,r=0;for(let s of e)r===o.length?o.push(i=new t(this.O(Te()),this.O(Te()),this,this.options)):i=o[r],i._$AI(s),r++;r<o.length&&(this._$AR(i&&i._$AB.nextSibling,r),o.length=r)}_$AR(e=this._$AA.nextSibling,o){for(this._$AP?.(!1,!0,o);e!==this._$AB;){let i=$i(e).nextSibling;$i(e).remove(),e=i}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},Gt=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,o,i,r,s){this.type=1,this._$AH=V,this._$AN=void 0,this.element=e,this.name=o,this._$AM=r,this.options=s,i.length>2||i[0]!==""||i[1]!==""?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=V}_$AI(e,o=this,i,r){let s=this.strings,l=!1;if(s===void 0)e=Yt(this,e,o,0),l=!Pe(e)||e!==this._$AH&&e!==X,l&&(this._$AH=e);else{let h=e,c,p;for(e=s[0],c=0;c<s.length-1;c++)p=Yt(this,h[i+c],o,c),p===X&&(p=this._$AH[c]),l||(l=!Pe(p)||p!==this._$AH[c]),p===V?e=V:e!==V&&(e+=(p??"")+s[c+1]),this._$AH[c]=p}l&&!r&&this.j(e)}j(e){e===V?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},ro=class extends Gt{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===V?void 0:e}},so=class extends Gt{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==V)}},lo=class extends Gt{constructor(e,o,i,r,s){super(e,o,i,r,s),this.type=5}_$AI(e,o=this){if((e=Yt(this,e,o,0)??V)===X)return;let i=this._$AH,r=e===V&&i!==V||e.capture!==i.capture||e.once!==i.once||e.passive!==i.passive,s=e!==V&&(i===V||r);r&&this.element.removeEventListener(this.name,this,i),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},no=class{constructor(e,o,i){this.element=e,this.type=6,this._$AN=void 0,this._$AM=o,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(e){Yt(this,e)}},Bi={M:Eo,P:zt,A:zo,C:1,L:Mi,R:io,D:Pi,V:Yt,I:re,H:Gt,N:so,U:lo,B:ro,F:no},Zs=Oe.litHtmlPolyfillSupport;Zs?.(Le,re),(Oe.litHtmlVersions??(Oe.litHtmlVersions=[])).push("3.3.3");Ii=(t,e,o)=>{let i=o?.renderBefore??e,r=i._$litPart$;if(r===void 0){let s=o?.renderBefore??null;i._$litPart$=r=new re(e.insertBefore(Te(),s),s,void 0,o??{})}return r._$AI(t),r}});var Re,Mt,Js,Fi=f(()=>{Ee();Ee();bt();bt();Re=globalThis,Mt=class extends Et{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){var o;let e=super.createRenderRoot();return(o=this.renderOptions).renderBefore??(o.renderBefore=e.firstChild),e}update(e){let o=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=Ii(o,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return X}};Mt._$litElement$=!0,Mt.finalized=!0,Re.litElementHydrateSupport?.({LitElement:Mt});Js=Re.litElementPolyfillSupport;Js?.({LitElement:Mt});(Re.litElementVersions??(Re.litElementVersions=[])).push("4.2.2")});var Hi=f(()=>{});var T=f(()=>{Ee();bt();Fi();Hi()});var Ni,Po=f(()=>{T();Ni=z`
  :host {
    display: block;
  }

  .input {
    flex: 1 1 auto;
    display: inline-flex;
    align-items: stretch;
    justify-content: start;
    position: relative;
    width: 100%;
    font-family: var(--sl-input-font-family);
    font-weight: var(--sl-input-font-weight);
    letter-spacing: var(--sl-input-letter-spacing);
    vertical-align: middle;
    overflow: hidden;
    cursor: text;
    transition:
      var(--sl-transition-fast) color,
      var(--sl-transition-fast) border,
      var(--sl-transition-fast) box-shadow,
      var(--sl-transition-fast) background-color;
  }

  /* Standard inputs */
  .input--standard {
    background-color: var(--sl-input-background-color);
    border: solid var(--sl-input-border-width) var(--sl-input-border-color);
  }

  .input--standard:hover:not(.input--disabled) {
    background-color: var(--sl-input-background-color-hover);
    border-color: var(--sl-input-border-color-hover);
  }

  .input--standard.input--focused:not(.input--disabled) {
    background-color: var(--sl-input-background-color-focus);
    border-color: var(--sl-input-border-color-focus);
    box-shadow: 0 0 0 var(--sl-focus-ring-width) var(--sl-input-focus-ring-color);
  }

  .input--standard.input--focused:not(.input--disabled) .input__control {
    color: var(--sl-input-color-focus);
  }

  .input--standard.input--disabled {
    background-color: var(--sl-input-background-color-disabled);
    border-color: var(--sl-input-border-color-disabled);
    opacity: 0.5;
    cursor: not-allowed;
  }

  .input--standard.input--disabled .input__control {
    color: var(--sl-input-color-disabled);
  }

  .input--standard.input--disabled .input__control::placeholder {
    color: var(--sl-input-placeholder-color-disabled);
  }

  /* Filled inputs */
  .input--filled {
    border: none;
    background-color: var(--sl-input-filled-background-color);
    color: var(--sl-input-color);
  }

  .input--filled:hover:not(.input--disabled) {
    background-color: var(--sl-input-filled-background-color-hover);
  }

  .input--filled.input--focused:not(.input--disabled) {
    background-color: var(--sl-input-filled-background-color-focus);
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  .input--filled.input--disabled {
    background-color: var(--sl-input-filled-background-color-disabled);
    opacity: 0.5;
    cursor: not-allowed;
  }

  .input__control {
    flex: 1 1 auto;
    font-family: inherit;
    font-size: inherit;
    font-weight: inherit;
    min-width: 0;
    height: 100%;
    color: var(--sl-input-color);
    border: none;
    background: inherit;
    box-shadow: none;
    padding: 0;
    margin: 0;
    cursor: inherit;
    -webkit-appearance: none;
  }

  .input__control::-webkit-search-decoration,
  .input__control::-webkit-search-cancel-button,
  .input__control::-webkit-search-results-button,
  .input__control::-webkit-search-results-decoration {
    -webkit-appearance: none;
  }

  .input__control:-webkit-autofill,
  .input__control:-webkit-autofill:hover,
  .input__control:-webkit-autofill:focus,
  .input__control:-webkit-autofill:active {
    box-shadow: 0 0 0 var(--sl-input-height-large) var(--sl-input-background-color-hover) inset !important;
    -webkit-text-fill-color: var(--sl-color-primary-500);
    caret-color: var(--sl-input-color);
  }

  .input--filled .input__control:-webkit-autofill,
  .input--filled .input__control:-webkit-autofill:hover,
  .input--filled .input__control:-webkit-autofill:focus,
  .input--filled .input__control:-webkit-autofill:active {
    box-shadow: 0 0 0 var(--sl-input-height-large) var(--sl-input-filled-background-color) inset !important;
  }

  .input__control::placeholder {
    color: var(--sl-input-placeholder-color);
    user-select: none;
    -webkit-user-select: none;
  }

  .input:hover:not(.input--disabled) .input__control {
    color: var(--sl-input-color-hover);
  }

  .input__control:focus {
    outline: none;
  }

  .input__prefix,
  .input__suffix {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    cursor: default;
  }

  .input__prefix ::slotted(sl-icon),
  .input__suffix ::slotted(sl-icon) {
    color: var(--sl-input-icon-color);
  }

  /*
   * Size modifiers
   */

  .input--small {
    border-radius: var(--sl-input-border-radius-small);
    font-size: var(--sl-input-font-size-small);
    height: var(--sl-input-height-small);
  }

  .input--small .input__control {
    height: calc(var(--sl-input-height-small) - var(--sl-input-border-width) * 2);
    padding: 0 var(--sl-input-spacing-small);
  }

  .input--small .input__clear,
  .input--small .input__password-toggle {
    width: calc(1em + var(--sl-input-spacing-small) * 2);
  }

  .input--small .input__prefix ::slotted(*) {
    margin-inline-start: var(--sl-input-spacing-small);
  }

  .input--small .input__suffix ::slotted(*) {
    margin-inline-end: var(--sl-input-spacing-small);
  }

  .input--medium {
    border-radius: var(--sl-input-border-radius-medium);
    font-size: var(--sl-input-font-size-medium);
    height: var(--sl-input-height-medium);
  }

  .input--medium .input__control {
    height: calc(var(--sl-input-height-medium) - var(--sl-input-border-width) * 2);
    padding: 0 var(--sl-input-spacing-medium);
  }

  .input--medium .input__clear,
  .input--medium .input__password-toggle {
    width: calc(1em + var(--sl-input-spacing-medium) * 2);
  }

  .input--medium .input__prefix ::slotted(*) {
    margin-inline-start: var(--sl-input-spacing-medium);
  }

  .input--medium .input__suffix ::slotted(*) {
    margin-inline-end: var(--sl-input-spacing-medium);
  }

  .input--large {
    border-radius: var(--sl-input-border-radius-large);
    font-size: var(--sl-input-font-size-large);
    height: var(--sl-input-height-large);
  }

  .input--large .input__control {
    height: calc(var(--sl-input-height-large) - var(--sl-input-border-width) * 2);
    padding: 0 var(--sl-input-spacing-large);
  }

  .input--large .input__clear,
  .input--large .input__password-toggle {
    width: calc(1em + var(--sl-input-spacing-large) * 2);
  }

  .input--large .input__prefix ::slotted(*) {
    margin-inline-start: var(--sl-input-spacing-large);
  }

  .input--large .input__suffix ::slotted(*) {
    margin-inline-end: var(--sl-input-spacing-large);
  }

  /*
   * Pill modifier
   */

  .input--pill.input--small {
    border-radius: var(--sl-input-height-small);
  }

  .input--pill.input--medium {
    border-radius: var(--sl-input-height-medium);
  }

  .input--pill.input--large {
    border-radius: var(--sl-input-height-large);
  }

  /*
   * Clearable + Password Toggle
   */

  .input__clear,
  .input__password-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: inherit;
    color: var(--sl-input-icon-color);
    border: none;
    background: none;
    padding: 0;
    transition: var(--sl-transition-fast) color;
    cursor: pointer;
  }

  .input__clear:hover,
  .input__password-toggle:hover {
    color: var(--sl-input-icon-color-hover);
  }

  .input__clear:focus,
  .input__password-toggle:focus {
    outline: none;
  }

  /* Don't show the browser's password toggle in Edge */
  ::-ms-reveal {
    display: none;
  }

  /* Hide the built-in number spinner */
  .input--no-spin-buttons input[type='number']::-webkit-outer-spin-button,
  .input--no-spin-buttons input[type='number']::-webkit-inner-spin-button {
    -webkit-appearance: none;
    display: none;
  }

  .input--no-spin-buttons input[type='number'] {
    -moz-appearance: textfield;
  }
`});var Bt,Ot=f(()=>{T();Bt=(t="value")=>(e,o)=>{let i=e.constructor,r=i.prototype.attributeChangedCallback;i.prototype.attributeChangedCallback=function(s,l,h){var c;let p=i.getPropertyOptions(t),u=typeof p.attribute=="string"?p.attribute:t;if(s===u){let d=p.converter||Dt,m=(typeof d=="function"?d:(c=d?.fromAttribute)!=null?c:Dt.fromAttribute)(h,p.type);this[t]!==m&&(this[o]=m)}r.call(this,s,l,h)}}});var yt,nt=f(()=>{T();yt=z`
  .form-control .form-control__label {
    display: none;
  }

  .form-control .form-control__help-text {
    display: none;
  }

  /* Label */
  .form-control--has-label .form-control__label {
    display: inline-block;
    color: var(--sl-input-label-color);
    margin-bottom: var(--sl-spacing-3x-small);
  }

  .form-control--has-label.form-control--small .form-control__label {
    font-size: var(--sl-input-label-font-size-small);
  }

  .form-control--has-label.form-control--medium .form-control__label {
    font-size: var(--sl-input-label-font-size-medium);
  }

  .form-control--has-label.form-control--large .form-control__label {
    font-size: var(--sl-input-label-font-size-large);
  }

  :host([required]) .form-control--has-label .form-control__label::after {
    content: var(--sl-input-required-content);
    margin-inline-start: var(--sl-input-required-content-offset);
    color: var(--sl-input-required-content-color);
  }

  /* Help text */
  .form-control--has-help-text .form-control__help-text {
    display: block;
    color: var(--sl-input-help-text-color);
    margin-top: var(--sl-spacing-3x-small);
  }

  .form-control--has-help-text.form-control--small .form-control__help-text {
    font-size: var(--sl-input-help-text-font-size-small);
  }

  .form-control--has-help-text.form-control--medium .form-control__help-text {
    font-size: var(--sl-input-help-text-font-size-medium);
  }

  .form-control--has-help-text.form-control--large .form-control__help-text {
    font-size: var(--sl-input-help-text-font-size-large);
  }

  .form-control--has-help-text.form-control--radio-group .form-control__help-text {
    margin-top: var(--sl-spacing-2x-small);
  }
`});var ji,Qs,tl,el,Ui,ol,il,Wi,qi,tt,It,n,Ki,Xi,Yi,Gi,M=f(()=>{ji=Object.defineProperty,Qs=Object.defineProperties,tl=Object.getOwnPropertyDescriptor,el=Object.getOwnPropertyDescriptors,Ui=Object.getOwnPropertySymbols,ol=Object.prototype.hasOwnProperty,il=Object.prototype.propertyIsEnumerable,Wi=t=>{throw TypeError(t)},qi=(t,e,o)=>e in t?ji(t,e,{enumerable:!0,configurable:!0,writable:!0,value:o}):t[e]=o,tt=(t,e)=>{for(var o in e||(e={}))ol.call(e,o)&&qi(t,o,e[o]);if(Ui)for(var o of Ui(e))il.call(e,o)&&qi(t,o,e[o]);return t},It=(t,e)=>Qs(t,el(e)),n=(t,e,o,i)=>{for(var r=i>1?void 0:i?tl(e,o):e,s=t.length-1,l;s>=0;s--)(l=t[s])&&(r=(i?l(e,o,r):l(r))||r);return i&&r&&ji(e,o,r),r},Ki=(t,e,o)=>e.has(t)||Wi("Cannot "+o),Xi=(t,e,o)=>(Ki(t,e,"read from private field"),o?o.call(t):e.get(t)),Yi=(t,e,o)=>e.has(t)?Wi("Cannot add the same private member more than once"):e instanceof WeakSet?e.add(t):e.set(t,o),Gi=(t,e,o,i)=>(Ki(t,e,"write to private field"),i?i.call(t,o):e.set(t,o),o)});var Ve,De,Me,Lo,ao,_t,Zi,mn,gn,at=f(()=>{M();Ve=new WeakMap,De=new WeakMap,Me=new WeakMap,Lo=new WeakSet,ao=new WeakMap,_t=class{constructor(t,e){this.handleFormData=o=>{let i=this.options.disabled(this.host),r=this.options.name(this.host),s=this.options.value(this.host),l=this.host.tagName.toLowerCase()==="sl-button";this.host.isConnected&&!i&&!l&&typeof r=="string"&&r.length>0&&typeof s<"u"&&(Array.isArray(s)?s.forEach(h=>{o.formData.append(r,h.toString())}):o.formData.append(r,s.toString()))},this.handleFormSubmit=o=>{var i;let r=this.options.disabled(this.host),s=this.options.reportValidity;this.form&&!this.form.noValidate&&((i=Ve.get(this.form))==null||i.forEach(l=>{this.setUserInteracted(l,!0)})),this.form&&!this.form.noValidate&&!r&&!s(this.host)&&(o.preventDefault(),o.stopImmediatePropagation())},this.handleFormReset=()=>{this.options.setValue(this.host,this.options.defaultValue(this.host)),this.setUserInteracted(this.host,!1),ao.set(this.host,[])},this.handleInteraction=o=>{let i=ao.get(this.host);i.includes(o.type)||i.push(o.type),i.length===this.options.assumeInteractionOn.length&&this.setUserInteracted(this.host,!0)},this.checkFormValidity=()=>{if(this.form&&!this.form.noValidate){let o=this.form.querySelectorAll("*");for(let i of o)if(typeof i.checkValidity=="function"&&!i.checkValidity())return!1}return!0},this.reportFormValidity=()=>{if(this.form&&!this.form.noValidate){let o=this.form.querySelectorAll("*");for(let i of o)if(typeof i.reportValidity=="function"&&!i.reportValidity())return!1}return!0},(this.host=t).addController(this),this.options=tt({form:o=>{let i=o.form;if(i){let s=o.getRootNode().querySelector(`#${i}`);if(s)return s}return o.closest("form")},name:o=>o.name,value:o=>o.value,defaultValue:o=>o.defaultValue,disabled:o=>{var i;return(i=o.disabled)!=null?i:!1},reportValidity:o=>typeof o.reportValidity=="function"?o.reportValidity():!0,checkValidity:o=>typeof o.checkValidity=="function"?o.checkValidity():!0,setValue:(o,i)=>o.value=i,assumeInteractionOn:["sl-input"]},e)}hostConnected(){let t=this.options.form(this.host);t&&this.attachForm(t),ao.set(this.host,[]),this.options.assumeInteractionOn.forEach(e=>{this.host.addEventListener(e,this.handleInteraction)})}hostDisconnected(){this.detachForm(),ao.delete(this.host),this.options.assumeInteractionOn.forEach(t=>{this.host.removeEventListener(t,this.handleInteraction)})}hostUpdated(){let t=this.options.form(this.host);t||this.detachForm(),t&&this.form!==t&&(this.detachForm(),this.attachForm(t)),this.host.hasUpdated&&this.setValidity(this.host.validity.valid)}attachForm(t){t?(this.form=t,Ve.has(this.form)?Ve.get(this.form).add(this.host):Ve.set(this.form,new Set([this.host])),this.form.addEventListener("formdata",this.handleFormData),this.form.addEventListener("submit",this.handleFormSubmit),this.form.addEventListener("reset",this.handleFormReset),De.has(this.form)||(De.set(this.form,this.form.reportValidity),this.form.reportValidity=()=>this.reportFormValidity()),Me.has(this.form)||(Me.set(this.form,this.form.checkValidity),this.form.checkValidity=()=>this.checkFormValidity())):this.form=void 0}detachForm(){if(!this.form)return;let t=Ve.get(this.form);t&&(t.delete(this.host),t.size<=0&&(this.form.removeEventListener("formdata",this.handleFormData),this.form.removeEventListener("submit",this.handleFormSubmit),this.form.removeEventListener("reset",this.handleFormReset),De.has(this.form)&&(this.form.reportValidity=De.get(this.form),De.delete(this.form)),Me.has(this.form)&&(this.form.checkValidity=Me.get(this.form),Me.delete(this.form)),this.form=void 0))}setUserInteracted(t,e){e?Lo.add(t):Lo.delete(t),t.requestUpdate()}doAction(t,e){if(this.form){let o=document.createElement("button");o.type=t,o.style.position="absolute",o.style.width="0",o.style.height="0",o.style.clipPath="inset(50%)",o.style.overflow="hidden",o.style.whiteSpace="nowrap",e&&(o.name=e.name,o.value=e.value,["formaction","formenctype","formmethod","formnovalidate","formtarget"].forEach(i=>{e.hasAttribute(i)&&o.setAttribute(i,e.getAttribute(i))})),this.form.append(o),o.click(),o.remove()}}getForm(){var t;return(t=this.form)!=null?t:null}reset(t){this.doAction("reset",t)}submit(t){this.doAction("submit",t)}setValidity(t){let e=this.host,o=!!Lo.has(e),i=!!e.required;e.toggleAttribute("data-required",i),e.toggleAttribute("data-optional",!i),e.toggleAttribute("data-invalid",!t),e.toggleAttribute("data-valid",t),e.toggleAttribute("data-user-invalid",!t&&o),e.toggleAttribute("data-user-valid",t&&o)}updateValidity(){let t=this.host;this.setValidity(t.validity.valid)}emitInvalidEvent(t){let e=new CustomEvent("sl-invalid",{bubbles:!1,composed:!1,cancelable:!0,detail:{}});t||e.preventDefault(),this.host.dispatchEvent(e)||t?.preventDefault()}},Zi=Object.freeze({badInput:!1,customError:!1,patternMismatch:!1,rangeOverflow:!1,rangeUnderflow:!1,stepMismatch:!1,tooLong:!1,tooShort:!1,typeMismatch:!1,valid:!0,valueMissing:!1}),mn=Object.freeze(It(tt({},Zi),{valid:!1,valueMissing:!0})),gn=Object.freeze(It(tt({},Zi),{valid:!1,customError:!0}))});var wt,ct=f(()=>{wt=class{constructor(t,...e){this.slotNames=[],this.handleSlotChange=o=>{let i=o.target;(this.slotNames.includes("[default]")&&!i.name||i.name&&this.slotNames.includes(i.name))&&this.host.requestUpdate()},(this.host=t).addController(this),this.slotNames=e}hasDefaultSlot(){return[...this.host.childNodes].some(t=>{if(t.nodeType===t.TEXT_NODE&&t.textContent.trim()!=="")return!0;if(t.nodeType===t.ELEMENT_NODE){let e=t;if(e.tagName.toLowerCase()==="sl-visually-hidden")return!1;if(!e.hasAttribute("slot"))return!0}return!1})}hasNamedSlot(t){return this.host.querySelector(`:scope > [slot="${t}"]`)!==null}test(t){return t==="[default]"?this.hasDefaultSlot():this.hasNamedSlot(t)}hostConnected(){this.host.shadowRoot.addEventListener("slotchange",this.handleSlotChange)}hostDisconnected(){this.host.shadowRoot.removeEventListener("slotchange",this.handleSlotChange)}}});function Be(...t){t.map(e=>{let o=e.$code.toLowerCase();se.has(o)?se.set(o,Object.assign(Object.assign({},se.get(o)),e)):se.set(o,e),Tt||(Tt=e)}),Qi()}function Qi(){Ji&&(Vo=document.documentElement.dir||"ltr",Do=document.documentElement.lang||navigator.language),[...Ro.keys()].map(t=>{typeof t.requestUpdate=="function"&&t.requestUpdate()})}var Ro,se,Tt,Vo,Do,Ji,co,ho=f(()=>{Ro=new Set,se=new Map,Vo="ltr",Do="en",Ji=typeof MutationObserver<"u"&&typeof document<"u"&&typeof document.documentElement<"u";if(Ji){let t=new MutationObserver(Qi);Vo=document.documentElement.dir||"ltr",Do=document.documentElement.lang||navigator.language,t.observe(document.documentElement,{attributes:!0,attributeFilter:["dir","lang"]})}co=class{constructor(e){this.host=e,this.host.addController(this)}hostConnected(){Ro.add(this.host)}hostDisconnected(){Ro.delete(this.host)}dir(){return`${this.host.dir||Vo}`.toLowerCase()}lang(){let e=`${this.host.lang||Do}`.toLowerCase().replace(/_/g,"-");try{return new Intl.Locale(e),e}catch{return Tt?Tt.$code.toLowerCase():"en"}}getTranslationData(e){var o,i;let r;try{r=new Intl.Locale(e.replace(/_/g,"-"))}catch{return{locale:void 0,language:"",region:"",primary:void 0,secondary:void 0}}let s=r.language.toLowerCase(),l=(i=(o=r.region)===null||o===void 0?void 0:o.toLowerCase())!==null&&i!==void 0?i:"",h=se.get(`${s}-${l}`),c=se.get(s);return{locale:r,language:s,region:l,primary:h,secondary:c}}exists(e,o){var i;let{primary:r,secondary:s}=this.getTranslationData((i=o.lang)!==null&&i!==void 0?i:this.lang());return o=Object.assign({includeFallback:!1},o),!!(r&&r[e]||s&&s[e]||o.includeFallback&&Tt&&Tt[e])}term(e,...o){let{primary:i,secondary:r}=this.getTranslationData(this.lang()),s;if(i&&i[e])s=i[e];else if(r&&r[e])s=r[e];else if(Tt&&Tt[e])s=Tt[e];else return console.error(`No translation found for: ${String(e)}`),String(e);return typeof s=="function"?s(...o):s}date(e,o){return e=new Date(e),new Intl.DateTimeFormat(this.lang(),o).format(e)}number(e,o){return e=Number(e),isNaN(e)?"":new Intl.NumberFormat(this.lang(),o).format(e)}relativeTime(e,o,i){return new Intl.RelativeTimeFormat(this.lang(),i).format(e,o)}}});var tr,er,le=f(()=>{ho();tr={$code:"en",$name:"English",$dir:"ltr",carousel:"Carousel",clearEntry:"Clear entry",close:"Close",copied:"Copied",copy:"Copy",currentValue:"Current value",error:"Error",goToSlide:(t,e)=>`Go to slide ${t} of ${e}`,hidePassword:"Hide password",loading:"Loading",nextSlide:"Next slide",numOptionsSelected:t=>t===0?"No options selected":t===1?"1 option selected":`${t} options selected`,previousSlide:"Previous slide",progress:"Progress",remove:"Remove",resize:"Resize",scrollToEnd:"Scroll to end",scrollToStart:"Scroll to start",selectAColorFromTheScreen:"Select a color from the screen",showPassword:"Show password",slideNum:t=>`Slide ${t}`,toggleColorFormat:"Toggle color format"};Be(tr);er=tr});var it,ht=f(()=>{le();ho();ho();it=class extends co{};Be(er)});function or(t){Mo=t}function ir(t=""){if(!Mo){let e=[...document.getElementsByTagName("script")],o=e.find(i=>i.hasAttribute("data-shoelace"));if(o)or(o.getAttribute("data-shoelace"));else{let i=e.find(s=>/shoelace(\.min)?\.js($|\?)/.test(s.src)||/shoelace-autoloader(\.min)?\.js($|\?)/.test(s.src)),r="";i&&(r=i.getAttribute("src")),or(r.split("/").slice(0,-1).join("/"))}}return Mo.replace(/\/$/,"")+(t?`/${t.replace(/^\//,"")}`:"")}var Mo,ne=f(()=>{Mo=""});var rl,rr,ae=f(()=>{ne();rl={name:"default",resolver:t=>ir(`assets/icons/${t}.svg`)},rr=rl});var sr,sl,lr,ce=f(()=>{sr={caret:`
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  `,check:`
    <svg part="checked-icon" class="checkbox__icon" viewBox="0 0 16 16">
      <g stroke="none" stroke-width="1" fill="none" fill-rule="evenodd" stroke-linecap="round">
        <g stroke="currentColor">
          <g transform="translate(3.428571, 3.428571)">
            <path d="M0,5.71428571 L3.42857143,9.14285714"></path>
            <path d="M9.14285714,0 L3.42857143,9.14285714"></path>
          </g>
        </g>
      </g>
    </svg>
  `,"chevron-down":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-chevron-down" viewBox="0 0 16 16">
      <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
    </svg>
  `,"chevron-left":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-chevron-left" viewBox="0 0 16 16">
      <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z"/>
    </svg>
  `,"chevron-right":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-chevron-right" viewBox="0 0 16 16">
      <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
    </svg>
  `,copy:`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-copy" viewBox="0 0 16 16">
      <path fill-rule="evenodd" d="M4 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V2Zm2-1a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H6ZM2 5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-1h1v1a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h1v1H2Z"/>
    </svg>
  `,eye:`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-eye" viewBox="0 0 16 16">
      <path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8zM1.173 8a13.133 13.133 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13.133 13.133 0 0 1 14.828 8c-.058.087-.122.183-.195.288-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5c-2.12 0-3.879-1.168-5.168-2.457A13.134 13.134 0 0 1 1.172 8z"/>
      <path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0z"/>
    </svg>
  `,"eye-slash":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-eye-slash" viewBox="0 0 16 16">
      <path d="M13.359 11.238C15.06 9.72 16 8 16 8s-3-5.5-8-5.5a7.028 7.028 0 0 0-2.79.588l.77.771A5.944 5.944 0 0 1 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13.134 13.134 0 0 1 14.828 8c-.058.087-.122.183-.195.288-.335.48-.83 1.12-1.465 1.755-.165.165-.337.328-.517.486l.708.709z"/>
      <path d="M11.297 9.176a3.5 3.5 0 0 0-4.474-4.474l.823.823a2.5 2.5 0 0 1 2.829 2.829l.822.822zm-2.943 1.299.822.822a3.5 3.5 0 0 1-4.474-4.474l.823.823a2.5 2.5 0 0 0 2.829 2.829z"/>
      <path d="M3.35 5.47c-.18.16-.353.322-.518.487A13.134 13.134 0 0 0 1.172 8l.195.288c.335.48.83 1.12 1.465 1.755C4.121 11.332 5.881 12.5 8 12.5c.716 0 1.39-.133 2.02-.36l.77.772A7.029 7.029 0 0 1 8 13.5C3 13.5 0 8 0 8s.939-1.721 2.641-3.238l.708.709zm10.296 8.884-12-12 .708-.708 12 12-.708.708z"/>
    </svg>
  `,eyedropper:`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-eyedropper" viewBox="0 0 16 16">
      <path d="M13.354.646a1.207 1.207 0 0 0-1.708 0L8.5 3.793l-.646-.647a.5.5 0 1 0-.708.708L8.293 5l-7.147 7.146A.5.5 0 0 0 1 12.5v1.793l-.854.853a.5.5 0 1 0 .708.707L1.707 15H3.5a.5.5 0 0 0 .354-.146L11 7.707l1.146 1.147a.5.5 0 0 0 .708-.708l-.647-.646 3.147-3.146a1.207 1.207 0 0 0 0-1.708l-2-2zM2 12.707l7-7L10.293 7l-7 7H2v-1.293z"></path>
    </svg>
  `,"grip-vertical":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-grip-vertical" viewBox="0 0 16 16">
      <path d="M7 2a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM7 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm-3 3a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm3 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"></path>
    </svg>
  `,indeterminate:`
    <svg part="indeterminate-icon" class="checkbox__icon" viewBox="0 0 16 16">
      <g stroke="none" stroke-width="1" fill="none" fill-rule="evenodd" stroke-linecap="round">
        <g stroke="currentColor" stroke-width="2">
          <g transform="translate(2.285714, 6.857143)">
            <path d="M10.2857143,1.14285714 L1.14285714,1.14285714"></path>
          </g>
        </g>
      </g>
    </svg>
  `,"person-fill":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-person-fill" viewBox="0 0 16 16">
      <path d="M3 14s-1 0-1-1 1-4 6-4 6 3 6 4-1 1-1 1H3zm5-6a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/>
    </svg>
  `,"play-fill":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-play-fill" viewBox="0 0 16 16">
      <path d="m11.596 8.697-6.363 3.692c-.54.313-1.233-.066-1.233-.697V4.308c0-.63.692-1.01 1.233-.696l6.363 3.692a.802.802 0 0 1 0 1.393z"></path>
    </svg>
  `,"pause-fill":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-pause-fill" viewBox="0 0 16 16">
      <path d="M5.5 3.5A1.5 1.5 0 0 1 7 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5zm5 0A1.5 1.5 0 0 1 12 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5z"></path>
    </svg>
  `,radio:`
    <svg part="checked-icon" class="radio__icon" viewBox="0 0 16 16">
      <g stroke="none" stroke-width="1" fill="none" fill-rule="evenodd">
        <g fill="currentColor">
          <circle cx="8" cy="8" r="3.42857143"></circle>
        </g>
      </g>
    </svg>
  `,"star-fill":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-star-fill" viewBox="0 0 16 16">
      <path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z"/>
    </svg>
  `,"x-lg":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-x-lg" viewBox="0 0 16 16">
      <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
    </svg>
  `,"x-circle-fill":`
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-x-circle-fill" viewBox="0 0 16 16">
      <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM5.354 4.646a.5.5 0 1 0-.708.708L7.293 8l-2.647 2.646a.5.5 0 0 0 .708.708L8 8.707l2.646 2.647a.5.5 0 0 0 .708-.708L8.707 8l2.647-2.646a.5.5 0 0 0-.708-.708L8 7.293 5.354 4.646z"></path>
    </svg>
  `},sl={name:"system",resolver:t=>t in sr?`data:image/svg+xml,${encodeURIComponent(sr[t])}`:""},lr=sl});function nr(t){Bo.push(t)}function ar(t){Bo=Bo.filter(e=>e!==t)}function Io(t){return ll.find(e=>e.name===t)}var ll,Bo,he=f(()=>{ae();ce();ll=[rr,lr],Bo=[]});var cr,pe=f(()=>{T();cr=z`
  :host {
    display: inline-block;
    width: 1em;
    height: 1em;
    box-sizing: content-box !important;
  }

  svg {
    display: block;
    height: 100%;
    width: 100%;
  }
`});function S(t,e){let o=tt({waitUntilFirstUpdate:!1},e);return(i,r)=>{let{update:s}=i,l=Array.isArray(t)?t:[t];i.update=function(h){l.forEach(c=>{let p=c;if(h.has(p)){let u=h.get(p),d=this[p];u!==d&&(!o.waitUntilFirstUpdate||this.hasUpdated)&&this[r](u,d)}}),s.call(this,h)}}}var Y=f(()=>{M()});var I,H=f(()=>{T();I=z`
  :host {
    box-sizing: border-box;
  }

  :host *,
  :host *::before,
  :host *::after {
    box-sizing: inherit;
  }

  [hidden] {
    display: none !important;
  }
`});var hr=f(()=>{});function a(t){return(e,o)=>typeof o=="object"?al(t,e,o):((i,r,s)=>{let l=r.hasOwnProperty(s);return r.constructor.createProperty(s,i),l?Object.getOwnPropertyDescriptor(r,s):void 0})(t,e,o)}var nl,al,Fo=f(()=>{Ee();nl={attribute:!0,type:String,converter:Dt,reflect:!1,hasChanged:eo},al=(t=nl,e,o)=>{let{kind:i,metadata:r}=o,s=globalThis.litPropertyMetadata.get(r);if(s===void 0&&globalThis.litPropertyMetadata.set(r,s=new Map),i==="setter"&&((t=Object.create(t)).wrapped=!0),s.set(o.name,t),i==="accessor"){let{name:l}=o;return{set(h){let c=e.get.call(this);e.set.call(this,h),this.requestUpdate(l,c,t,!0,h)},init(h){return h!==void 0&&this.C(l,void 0,t,h),h}}}if(i==="setter"){let{name:l}=o;return function(h){let c=this[l];e.call(this,h),this.requestUpdate(l,c,t,!0,h)}}throw Error("Unsupported decorator location: "+i)}});function B(t){return a({...t,state:!0,attribute:!1})}var pr=f(()=>{Fo();});var dr=f(()=>{});var Zt,de=f(()=>{Zt=(t,e,o)=>(o.configurable=!0,o.enumerable=!0,Reflect.decorate&&typeof e!="object"&&Object.defineProperty(t,e,o),o)});function P(t,e){return(o,i,r)=>{let s=l=>l.renderRoot?.querySelector(t)??null;if(e){let{get:l,set:h}=typeof i=="object"?o:r??(()=>{let c=Symbol();return{get(){return this[c]},set(p){this[c]=p}}})();return Zt(o,i,{get(){let c=l.call(this);return c===void 0&&(c=s(this),(c!==null||this.hasUpdated)&&h.call(this,c)),c}})}return Zt(o,i,{get(){return s(this)}})}}var ur=f(()=>{de();});var fr=f(()=>{de();});var mr=f(()=>{de();});var gr=f(()=>{de();});var vr=f(()=>{de();});var et=f(()=>{hr();Fo();pr();dr();ur();fr();mr();gr();vr()});var po,L,N=f(()=>{M();T();et();L=class extends Mt{constructor(){super(),Yi(this,po,!1),this.initialReflectedProperties=new Map,Object.entries(this.constructor.dependencies).forEach(([t,e])=>{this.constructor.define(t,e)})}emit(t,e){let o=new CustomEvent(t,tt({bubbles:!0,cancelable:!1,composed:!0,detail:{}},e));return this.dispatchEvent(o),o}static define(t,e=this,o={}){let i=customElements.get(t);if(!i){try{customElements.define(t,e,o)}catch{customElements.define(t,class extends e{},o)}return}let r=" (unknown version)",s=r;"version"in e&&e.version&&(r=" v"+e.version),"version"in i&&i.version&&(s=" v"+i.version),!(r&&s&&r===s)&&console.warn(`Attempted to register <${t}>${r}, but <${t}>${s} has already been registered.`)}attributeChangedCallback(t,e,o){Xi(this,po)||(this.constructor.elementProperties.forEach((i,r)=>{i.reflect&&this[r]!=null&&this.initialReflectedProperties.set(r,this[r])}),Gi(this,po,!0)),super.attributeChangedCallback(t,e,o)}willUpdate(t){super.willUpdate(t),this.initialReflectedProperties.forEach((e,o)=>{t.has(o)&&this[o]==null&&(this[o]=e)})}};po=new WeakMap;L.version="2.20.1";L.dependencies={};n([a()],L.prototype,"dir",2);n([a()],L.prototype,"lang",2)});var xa,br,yr,cl,_r,Ho=f(()=>{bt();({I:xa}=Bi),br=(t,e)=>e===void 0?t?._$litType$!==void 0:t?._$litType$===e,yr=t=>t.strings===void 0,cl={},_r=(t,e=cl)=>t._$AH=e});var wr=f(()=>{Ho()});var Ie,uo,No,Uo,q,xt=f(()=>{he();pe();Y();H();N();M();T();wr();et();Ie=Symbol(),uo=Symbol(),Uo=new Map,q=class extends L{constructor(){super(...arguments),this.initialRender=!1,this.svg=null,this.label="",this.library="default"}async resolveIcon(t,e){var o;let i;if(e?.spriteSheet)return this.svg=x`<svg part="svg">
        <use part="use" href="${t}"></use>
      </svg>`,this.svg;try{if(i=await fetch(t,{mode:"cors"}),!i.ok)return i.status===410?Ie:uo}catch{return uo}try{let r=document.createElement("div");r.innerHTML=await i.text();let s=r.firstElementChild;if(((o=s?.tagName)==null?void 0:o.toLowerCase())!=="svg")return Ie;No||(No=new DOMParser);let h=No.parseFromString(s.outerHTML,"text/html").body.querySelector("svg");return h?(h.part.add("svg"),document.adoptNode(h)):Ie}catch{return Ie}}connectedCallback(){super.connectedCallback(),nr(this)}firstUpdated(){this.initialRender=!0,this.setIcon()}disconnectedCallback(){super.disconnectedCallback(),ar(this)}getIconSource(){let t=Io(this.library);return this.name&&t?{url:t.resolver(this.name),fromLibrary:!0}:{url:this.src,fromLibrary:!1}}handleLabelChange(){typeof this.label=="string"&&this.label.length>0?(this.setAttribute("role","img"),this.setAttribute("aria-label",this.label),this.removeAttribute("aria-hidden")):(this.removeAttribute("role"),this.removeAttribute("aria-label"),this.setAttribute("aria-hidden","true"))}async setIcon(){var t;let{url:e,fromLibrary:o}=this.getIconSource(),i=o?Io(this.library):void 0;if(!e){this.svg=null;return}let r=Uo.get(e);if(r||(r=this.resolveIcon(e,i),Uo.set(e,r)),!this.initialRender)return;let s=await r;if(s===uo&&Uo.delete(e),e===this.getIconSource().url){if(br(s)){if(this.svg=s,i){await this.updateComplete;let l=this.shadowRoot.querySelector("[part='svg']");typeof i.mutator=="function"&&l&&i.mutator(l)}return}switch(s){case uo:case Ie:this.svg=null,this.emit("sl-error");break;default:this.svg=s.cloneNode(!0),(t=i?.mutator)==null||t.call(i,this.svg),this.emit("sl-load")}}}render(){return this.svg}};q.styles=[I,cr];n([B()],q.prototype,"svg",2);n([a({reflect:!0})],q.prototype,"name",2);n([a()],q.prototype,"src",2);n([a()],q.prototype,"label",2);n([a({reflect:!0})],q.prototype,"library",2);n([S("label")],q.prototype,"handleLabelChange",1);n([S(["name","src","library"])],q.prototype,"setIcon",1)});var pt,ue,Ft,fo=f(()=>{pt={ATTRIBUTE:1,CHILD:2,PROPERTY:3,BOOLEAN_ATTRIBUTE:4,EVENT:5,ELEMENT:6},ue=t=>(...e)=>({_$litDirective$:t,values:e}),Ft=class{constructor(e){}get _$AU(){return this._$AM._$AU}_$AT(e,o,i){this._$Ct=e,this._$AM=o,this._$Ci=i}_$AS(e,o){return this.update(e,o)}update(e,o){return this.render(...o)}}});var R,xr=f(()=>{bt();fo();R=ue(class extends Ft{constructor(t){if(super(t),t.type!==pt.ATTRIBUTE||t.name!=="class"||t.strings?.length>2)throw Error("`classMap()` can only be used in the `class` attribute and must be the only part in the attribute.")}render(t){return" "+Object.keys(t).filter(e=>t[e]).join(" ")+" "}update(t,[e]){if(this.st===void 0){this.st=new Set,t.strings!==void 0&&(this.nt=new Set(t.strings.join(" ").split(/\s/).filter(i=>i!=="")));for(let i in e)e[i]&&!this.nt?.has(i)&&this.st.add(i);return this.render(e)}let o=t.element.classList;for(let i of this.st)i in e||(o.remove(i),this.st.delete(i));for(let i in e){let r=!!e[i];r===this.st.has(i)||this.nt?.has(i)||(r?(o.add(i),this.st.add(i)):(o.remove(i),this.st.delete(i)))}return X}})});var dt=f(()=>{xr()});var y,Cr=f(()=>{bt();y=t=>t??V});var fe=f(()=>{Cr()});var Pt,kr=f(()=>{bt();fo();Ho();Pt=ue(class extends Ft{constructor(t){if(super(t),t.type!==pt.PROPERTY&&t.type!==pt.ATTRIBUTE&&t.type!==pt.BOOLEAN_ATTRIBUTE)throw Error("The `live` directive is not allowed on child or event bindings");if(!yr(t))throw Error("`live` bindings can only contain a single expression")}render(t){return t}update(t,[e]){if(e===X||e===V)return e;let o=t.element,i=t.name;if(t.type===pt.PROPERTY){if(e===o[i])return X}else if(t.type===pt.BOOLEAN_ATTRIBUTE){if(!!e===o.hasAttribute(i))return X}else if(t.type===pt.ATTRIBUTE&&o.getAttribute(i)===e+"")return X;return _r(t),e}})});var Fe=f(()=>{kr()});var b,qo=f(()=>{Po();Ot();nt();at();ct();ht();xt();Y();H();N();M();dt();T();fe();Fe();et();b=class extends L{constructor(){super(...arguments),this.formControlController=new _t(this,{assumeInteractionOn:["sl-blur","sl-input"]}),this.hasSlotController=new wt(this,"help-text","label"),this.localize=new it(this),this.hasFocus=!1,this.title="",this.__numberInput=Object.assign(document.createElement("input"),{type:"number"}),this.__dateInput=Object.assign(document.createElement("input"),{type:"date"}),this.type="text",this.name="",this.value="",this.defaultValue="",this.size="medium",this.filled=!1,this.pill=!1,this.label="",this.helpText="",this.clearable=!1,this.disabled=!1,this.placeholder="",this.readonly=!1,this.passwordToggle=!1,this.passwordVisible=!1,this.noSpinButtons=!1,this.form="",this.required=!1,this.spellcheck=!0}get valueAsDate(){var t;return this.__dateInput.type=this.type,this.__dateInput.value=this.value,((t=this.input)==null?void 0:t.valueAsDate)||this.__dateInput.valueAsDate}set valueAsDate(t){this.__dateInput.type=this.type,this.__dateInput.valueAsDate=t,this.value=this.__dateInput.value}get valueAsNumber(){var t;return this.__numberInput.value=this.value,((t=this.input)==null?void 0:t.valueAsNumber)||this.__numberInput.valueAsNumber}set valueAsNumber(t){this.__numberInput.valueAsNumber=t,this.value=this.__numberInput.value}get validity(){return this.input.validity}get validationMessage(){return this.input.validationMessage}firstUpdated(){this.formControlController.updateValidity()}handleBlur(){this.hasFocus=!1,this.emit("sl-blur")}handleChange(){this.value=this.input.value,this.emit("sl-change")}handleClearClick(t){t.preventDefault(),this.value!==""&&(this.value="",this.emit("sl-clear"),this.emit("sl-input"),this.emit("sl-change")),this.input.focus()}handleFocus(){this.hasFocus=!0,this.emit("sl-focus")}handleInput(){this.value=this.input.value,this.formControlController.updateValidity(),this.emit("sl-input")}handleInvalid(t){this.formControlController.setValidity(!1),this.formControlController.emitInvalidEvent(t)}handleKeyDown(t){let e=t.metaKey||t.ctrlKey||t.shiftKey||t.altKey;t.key==="Enter"&&!e&&setTimeout(()=>{!t.defaultPrevented&&!t.isComposing&&this.formControlController.submit()})}handlePasswordToggle(){this.passwordVisible=!this.passwordVisible}handleDisabledChange(){this.formControlController.setValidity(this.disabled)}handleStepChange(){this.input.step=String(this.step),this.formControlController.updateValidity()}async handleValueChange(){await this.updateComplete,this.formControlController.updateValidity()}focus(t){this.input.focus(t)}blur(){this.input.blur()}select(){this.input.select()}setSelectionRange(t,e,o="none"){this.input.setSelectionRange(t,e,o)}setRangeText(t,e,o,i="preserve"){let r=e??this.input.selectionStart,s=o??this.input.selectionEnd;this.input.setRangeText(t,r,s,i),this.value!==this.input.value&&(this.value=this.input.value)}showPicker(){"showPicker"in HTMLInputElement.prototype&&this.input.showPicker()}stepUp(){this.input.stepUp(),this.value!==this.input.value&&(this.value=this.input.value)}stepDown(){this.input.stepDown(),this.value!==this.input.value&&(this.value=this.input.value)}checkValidity(){return this.input.checkValidity()}getForm(){return this.formControlController.getForm()}reportValidity(){return this.input.reportValidity()}setCustomValidity(t){this.input.setCustomValidity(t),this.formControlController.updateValidity()}render(){let t=this.hasSlotController.test("label"),e=this.hasSlotController.test("help-text"),o=this.label?!0:!!t,i=this.helpText?!0:!!e,s=this.clearable&&!this.disabled&&!this.readonly&&(typeof this.value=="number"||this.value.length>0);return x`
      <div
        part="form-control"
        class=${R({"form-control":!0,"form-control--small":this.size==="small","form-control--medium":this.size==="medium","form-control--large":this.size==="large","form-control--has-label":o,"form-control--has-help-text":i})}
      >
        <label
          part="form-control-label"
          class="form-control__label"
          for="input"
          aria-hidden=${o?"false":"true"}
        >
          <slot name="label">${this.label}</slot>
        </label>

        <div part="form-control-input" class="form-control-input">
          <div
            part="base"
            class=${R({input:!0,"input--small":this.size==="small","input--medium":this.size==="medium","input--large":this.size==="large","input--pill":this.pill,"input--standard":!this.filled,"input--filled":this.filled,"input--disabled":this.disabled,"input--focused":this.hasFocus,"input--empty":!this.value,"input--no-spin-buttons":this.noSpinButtons})}
          >
            <span part="prefix" class="input__prefix">
              <slot name="prefix"></slot>
            </span>

            <input
              part="input"
              id="input"
              class="input__control"
              type=${this.type==="password"&&this.passwordVisible?"text":this.type}
              title=${this.title}
              name=${y(this.name)}
              ?disabled=${this.disabled}
              ?readonly=${this.readonly}
              ?required=${this.required}
              placeholder=${y(this.placeholder)}
              minlength=${y(this.minlength)}
              maxlength=${y(this.maxlength)}
              min=${y(this.min)}
              max=${y(this.max)}
              step=${y(this.step)}
              .value=${Pt(this.value)}
              autocapitalize=${y(this.autocapitalize)}
              autocomplete=${y(this.autocomplete)}
              autocorrect=${y(this.autocorrect)}
              ?autofocus=${this.autofocus}
              spellcheck=${this.spellcheck}
              pattern=${y(this.pattern)}
              enterkeyhint=${y(this.enterkeyhint)}
              inputmode=${y(this.inputmode)}
              aria-describedby="help-text"
              @change=${this.handleChange}
              @input=${this.handleInput}
              @invalid=${this.handleInvalid}
              @keydown=${this.handleKeyDown}
              @focus=${this.handleFocus}
              @blur=${this.handleBlur}
            />

            ${s?x`
                  <button
                    part="clear-button"
                    class="input__clear"
                    type="button"
                    aria-label=${this.localize.term("clearEntry")}
                    @click=${this.handleClearClick}
                    tabindex="-1"
                  >
                    <slot name="clear-icon">
                      <sl-icon name="x-circle-fill" library="system"></sl-icon>
                    </slot>
                  </button>
                `:""}
            ${this.passwordToggle&&!this.disabled?x`
                  <button
                    part="password-toggle-button"
                    class="input__password-toggle"
                    type="button"
                    aria-label=${this.localize.term(this.passwordVisible?"hidePassword":"showPassword")}
                    @click=${this.handlePasswordToggle}
                    tabindex="-1"
                  >
                    ${this.passwordVisible?x`
                          <slot name="show-password-icon">
                            <sl-icon name="eye-slash" library="system"></sl-icon>
                          </slot>
                        `:x`
                          <slot name="hide-password-icon">
                            <sl-icon name="eye" library="system"></sl-icon>
                          </slot>
                        `}
                  </button>
                `:""}

            <span part="suffix" class="input__suffix">
              <slot name="suffix"></slot>
            </span>
          </div>
        </div>

        <div
          part="form-control-help-text"
          id="help-text"
          class="form-control__help-text"
          aria-hidden=${i?"false":"true"}
        >
          <slot name="help-text">${this.helpText}</slot>
        </div>
      </div>
    `}};b.styles=[I,yt,Ni];b.dependencies={"sl-icon":q};n([P(".input__control")],b.prototype,"input",2);n([B()],b.prototype,"hasFocus",2);n([a()],b.prototype,"title",2);n([a({reflect:!0})],b.prototype,"type",2);n([a()],b.prototype,"name",2);n([a()],b.prototype,"value",2);n([Bt()],b.prototype,"defaultValue",2);n([a({reflect:!0})],b.prototype,"size",2);n([a({type:Boolean,reflect:!0})],b.prototype,"filled",2);n([a({type:Boolean,reflect:!0})],b.prototype,"pill",2);n([a()],b.prototype,"label",2);n([a({attribute:"help-text"})],b.prototype,"helpText",2);n([a({type:Boolean})],b.prototype,"clearable",2);n([a({type:Boolean,reflect:!0})],b.prototype,"disabled",2);n([a()],b.prototype,"placeholder",2);n([a({type:Boolean,reflect:!0})],b.prototype,"readonly",2);n([a({attribute:"password-toggle",type:Boolean})],b.prototype,"passwordToggle",2);n([a({attribute:"password-visible",type:Boolean})],b.prototype,"passwordVisible",2);n([a({attribute:"no-spin-buttons",type:Boolean})],b.prototype,"noSpinButtons",2);n([a({reflect:!0})],b.prototype,"form",2);n([a({type:Boolean,reflect:!0})],b.prototype,"required",2);n([a()],b.prototype,"pattern",2);n([a({type:Number})],b.prototype,"minlength",2);n([a({type:Number})],b.prototype,"maxlength",2);n([a()],b.prototype,"min",2);n([a()],b.prototype,"max",2);n([a()],b.prototype,"step",2);n([a()],b.prototype,"autocapitalize",2);n([a()],b.prototype,"autocorrect",2);n([a()],b.prototype,"autocomplete",2);n([a({type:Boolean})],b.prototype,"autofocus",2);n([a()],b.prototype,"enterkeyhint",2);n([a({type:Boolean,converter:{fromAttribute:t=>!(!t||t==="false"),toAttribute:t=>t?"true":"false"}})],b.prototype,"spellcheck",2);n([a()],b.prototype,"inputmode",2);n([S("disabled",{waitUntilFirstUpdate:!0})],b.prototype,"handleDisabledChange",1);n([S("step",{waitUntilFirstUpdate:!0})],b.prototype,"handleStepChange",1);n([S("value",{waitUntilFirstUpdate:!0})],b.prototype,"handleValueChange",1)});var $r=f(()=>{qo();b.define("sl-input")});var Sr=f(()=>{$r();qo();Po();Ot();nt();at();ct();ht();le();xt();he();ae();ce();pe();ne();Y();H();N();M()});var Ar,jo=f(()=>{T();Ar=z`
  :host {
    display: block;
  }

  .textarea {
    display: grid;
    align-items: center;
    position: relative;
    width: 100%;
    font-family: var(--sl-input-font-family);
    font-weight: var(--sl-input-font-weight);
    line-height: var(--sl-line-height-normal);
    letter-spacing: var(--sl-input-letter-spacing);
    vertical-align: middle;
    transition:
      var(--sl-transition-fast) color,
      var(--sl-transition-fast) border,
      var(--sl-transition-fast) box-shadow,
      var(--sl-transition-fast) background-color;
    cursor: text;
  }

  /* Standard textareas */
  .textarea--standard {
    background-color: var(--sl-input-background-color);
    border: solid var(--sl-input-border-width) var(--sl-input-border-color);
  }

  .textarea--standard:hover:not(.textarea--disabled) {
    background-color: var(--sl-input-background-color-hover);
    border-color: var(--sl-input-border-color-hover);
  }
  .textarea--standard:hover:not(.textarea--disabled) .textarea__control {
    color: var(--sl-input-color-hover);
  }

  .textarea--standard.textarea--focused:not(.textarea--disabled) {
    background-color: var(--sl-input-background-color-focus);
    border-color: var(--sl-input-border-color-focus);
    color: var(--sl-input-color-focus);
    box-shadow: 0 0 0 var(--sl-focus-ring-width) var(--sl-input-focus-ring-color);
  }

  .textarea--standard.textarea--focused:not(.textarea--disabled) .textarea__control {
    color: var(--sl-input-color-focus);
  }

  .textarea--standard.textarea--disabled {
    background-color: var(--sl-input-background-color-disabled);
    border-color: var(--sl-input-border-color-disabled);
    opacity: 0.5;
    cursor: not-allowed;
  }

  .textarea__control,
  .textarea__size-adjuster {
    grid-area: 1 / 1 / 2 / 2;
  }

  .textarea__size-adjuster {
    visibility: hidden;
    pointer-events: none;
    opacity: 0;
  }

  .textarea--standard.textarea--disabled .textarea__control {
    color: var(--sl-input-color-disabled);
  }

  .textarea--standard.textarea--disabled .textarea__control::placeholder {
    color: var(--sl-input-placeholder-color-disabled);
  }

  /* Filled textareas */
  .textarea--filled {
    border: none;
    background-color: var(--sl-input-filled-background-color);
    color: var(--sl-input-color);
  }

  .textarea--filled:hover:not(.textarea--disabled) {
    background-color: var(--sl-input-filled-background-color-hover);
  }

  .textarea--filled.textarea--focused:not(.textarea--disabled) {
    background-color: var(--sl-input-filled-background-color-focus);
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  .textarea--filled.textarea--disabled {
    background-color: var(--sl-input-filled-background-color-disabled);
    opacity: 0.5;
    cursor: not-allowed;
  }

  .textarea__control {
    font-family: inherit;
    font-size: inherit;
    font-weight: inherit;
    line-height: 1.4;
    color: var(--sl-input-color);
    border: none;
    background: none;
    box-shadow: none;
    cursor: inherit;
    -webkit-appearance: none;
  }

  .textarea__control::-webkit-search-decoration,
  .textarea__control::-webkit-search-cancel-button,
  .textarea__control::-webkit-search-results-button,
  .textarea__control::-webkit-search-results-decoration {
    -webkit-appearance: none;
  }

  .textarea__control::placeholder {
    color: var(--sl-input-placeholder-color);
    user-select: none;
    -webkit-user-select: none;
  }

  .textarea__control:focus {
    outline: none;
  }

  /*
   * Size modifiers
   */

  .textarea--small {
    border-radius: var(--sl-input-border-radius-small);
    font-size: var(--sl-input-font-size-small);
  }

  .textarea--small .textarea__control {
    padding: 0.5em var(--sl-input-spacing-small);
  }

  .textarea--medium {
    border-radius: var(--sl-input-border-radius-medium);
    font-size: var(--sl-input-font-size-medium);
  }

  .textarea--medium .textarea__control {
    padding: 0.5em var(--sl-input-spacing-medium);
  }

  .textarea--large {
    border-radius: var(--sl-input-border-radius-large);
    font-size: var(--sl-input-font-size-large);
  }

  .textarea--large .textarea__control {
    padding: 0.5em var(--sl-input-spacing-large);
  }

  /*
   * Resize types
   */

  .textarea--resize-none .textarea__control {
    resize: none;
  }

  .textarea--resize-vertical .textarea__control {
    resize: vertical;
  }

  .textarea--resize-auto .textarea__control {
    height: auto;
    resize: none;
    overflow-y: hidden;
  }
`});var $,Wo=f(()=>{jo();Ot();nt();at();ct();Y();H();N();M();dt();T();fe();Fe();et();$=class extends L{constructor(){super(...arguments),this.formControlController=new _t(this,{assumeInteractionOn:["sl-blur","sl-input"]}),this.hasSlotController=new wt(this,"help-text","label"),this.hasFocus=!1,this.title="",this.name="",this.value="",this.size="medium",this.filled=!1,this.label="",this.helpText="",this.placeholder="",this.rows=4,this.resize="vertical",this.disabled=!1,this.readonly=!1,this.form="",this.required=!1,this.spellcheck=!0,this.defaultValue=""}get validity(){return this.input.validity}get validationMessage(){return this.input.validationMessage}connectedCallback(){super.connectedCallback(),this.resizeObserver=new ResizeObserver(()=>this.setTextareaHeight()),this.updateComplete.then(()=>{this.setTextareaHeight(),this.resizeObserver.observe(this.input)})}firstUpdated(){this.formControlController.updateValidity()}disconnectedCallback(){var t;super.disconnectedCallback(),this.input&&((t=this.resizeObserver)==null||t.unobserve(this.input))}handleBlur(){this.hasFocus=!1,this.emit("sl-blur")}handleChange(){this.value=this.input.value,this.setTextareaHeight(),this.emit("sl-change")}handleFocus(){this.hasFocus=!0,this.emit("sl-focus")}handleInput(){this.value=this.input.value,this.emit("sl-input")}handleInvalid(t){this.formControlController.setValidity(!1),this.formControlController.emitInvalidEvent(t)}setTextareaHeight(){this.resize==="auto"?(this.sizeAdjuster.style.height=`${this.input.clientHeight}px`,this.input.style.height="auto",this.input.style.height=`${this.input.scrollHeight}px`):this.input.style.height=""}handleDisabledChange(){this.formControlController.setValidity(this.disabled)}handleRowsChange(){this.setTextareaHeight()}async handleValueChange(){await this.updateComplete,this.formControlController.updateValidity(),this.setTextareaHeight()}focus(t){this.input.focus(t)}blur(){this.input.blur()}select(){this.input.select()}scrollPosition(t){if(t){typeof t.top=="number"&&(this.input.scrollTop=t.top),typeof t.left=="number"&&(this.input.scrollLeft=t.left);return}return{top:this.input.scrollTop,left:this.input.scrollTop}}setSelectionRange(t,e,o="none"){this.input.setSelectionRange(t,e,o)}setRangeText(t,e,o,i="preserve"){let r=e??this.input.selectionStart,s=o??this.input.selectionEnd;this.input.setRangeText(t,r,s,i),this.value!==this.input.value&&(this.value=this.input.value,this.setTextareaHeight())}checkValidity(){return this.input.checkValidity()}getForm(){return this.formControlController.getForm()}reportValidity(){return this.input.reportValidity()}setCustomValidity(t){this.input.setCustomValidity(t),this.formControlController.updateValidity()}render(){let t=this.hasSlotController.test("label"),e=this.hasSlotController.test("help-text"),o=this.label?!0:!!t,i=this.helpText?!0:!!e;return x`
      <div
        part="form-control"
        class=${R({"form-control":!0,"form-control--small":this.size==="small","form-control--medium":this.size==="medium","form-control--large":this.size==="large","form-control--has-label":o,"form-control--has-help-text":i})}
      >
        <label
          part="form-control-label"
          class="form-control__label"
          for="input"
          aria-hidden=${o?"false":"true"}
        >
          <slot name="label">${this.label}</slot>
        </label>

        <div part="form-control-input" class="form-control-input">
          <div
            part="base"
            class=${R({textarea:!0,"textarea--small":this.size==="small","textarea--medium":this.size==="medium","textarea--large":this.size==="large","textarea--standard":!this.filled,"textarea--filled":this.filled,"textarea--disabled":this.disabled,"textarea--focused":this.hasFocus,"textarea--empty":!this.value,"textarea--resize-none":this.resize==="none","textarea--resize-vertical":this.resize==="vertical","textarea--resize-auto":this.resize==="auto"})}
          >
            <textarea
              part="textarea"
              id="input"
              class="textarea__control"
              title=${this.title}
              name=${y(this.name)}
              .value=${Pt(this.value)}
              ?disabled=${this.disabled}
              ?readonly=${this.readonly}
              ?required=${this.required}
              placeholder=${y(this.placeholder)}
              rows=${y(this.rows)}
              minlength=${y(this.minlength)}
              maxlength=${y(this.maxlength)}
              autocapitalize=${y(this.autocapitalize)}
              autocorrect=${y(this.autocorrect)}
              ?autofocus=${this.autofocus}
              spellcheck=${y(this.spellcheck)}
              enterkeyhint=${y(this.enterkeyhint)}
              inputmode=${y(this.inputmode)}
              aria-describedby="help-text"
              @change=${this.handleChange}
              @input=${this.handleInput}
              @invalid=${this.handleInvalid}
              @focus=${this.handleFocus}
              @blur=${this.handleBlur}
            ></textarea>
            <!-- This "adjuster" exists to prevent layout shifting. https://github.com/shoelace-style/shoelace/issues/2180 -->
            <div part="textarea-adjuster" class="textarea__size-adjuster" ?hidden=${this.resize!=="auto"}></div>
          </div>
        </div>

        <div
          part="form-control-help-text"
          id="help-text"
          class="form-control__help-text"
          aria-hidden=${i?"false":"true"}
        >
          <slot name="help-text">${this.helpText}</slot>
        </div>
      </div>
    `}};$.styles=[I,yt,Ar];n([P(".textarea__control")],$.prototype,"input",2);n([P(".textarea__size-adjuster")],$.prototype,"sizeAdjuster",2);n([B()],$.prototype,"hasFocus",2);n([a()],$.prototype,"title",2);n([a()],$.prototype,"name",2);n([a()],$.prototype,"value",2);n([a({reflect:!0})],$.prototype,"size",2);n([a({type:Boolean,reflect:!0})],$.prototype,"filled",2);n([a()],$.prototype,"label",2);n([a({attribute:"help-text"})],$.prototype,"helpText",2);n([a()],$.prototype,"placeholder",2);n([a({type:Number})],$.prototype,"rows",2);n([a()],$.prototype,"resize",2);n([a({type:Boolean,reflect:!0})],$.prototype,"disabled",2);n([a({type:Boolean,reflect:!0})],$.prototype,"readonly",2);n([a({reflect:!0})],$.prototype,"form",2);n([a({type:Boolean,reflect:!0})],$.prototype,"required",2);n([a({type:Number})],$.prototype,"minlength",2);n([a({type:Number})],$.prototype,"maxlength",2);n([a()],$.prototype,"autocapitalize",2);n([a()],$.prototype,"autocorrect",2);n([a()],$.prototype,"autocomplete",2);n([a({type:Boolean})],$.prototype,"autofocus",2);n([a()],$.prototype,"enterkeyhint",2);n([a({type:Boolean,converter:{fromAttribute:t=>!(!t||t==="false"),toAttribute:t=>t?"true":"false"}})],$.prototype,"spellcheck",2);n([a()],$.prototype,"inputmode",2);n([Bt()],$.prototype,"defaultValue",2);n([S("disabled",{waitUntilFirstUpdate:!0})],$.prototype,"handleDisabledChange",1);n([S("rows",{waitUntilFirstUpdate:!0})],$.prototype,"handleRowsChange",1);n([S("value",{waitUntilFirstUpdate:!0})],$.prototype,"handleValueChange",1)});var Er=f(()=>{Wo();$.define("sl-textarea")});var zr=f(()=>{Er();Wo();jo();Ot();nt();at();ct();Y();H();N();M()});var Or,Ko=f(()=>{T();Or=z`
  :host {
    display: inline-block;
  }

  .tag {
    display: flex;
    align-items: center;
    border: solid 1px;
    line-height: 1;
    white-space: nowrap;
    user-select: none;
    -webkit-user-select: none;
  }

  .tag__remove::part(base) {
    color: inherit;
    padding: 0;
  }

  /*
   * Variant modifiers
   */

  .tag--primary {
    background-color: var(--sl-color-primary-50);
    border-color: var(--sl-color-primary-200);
    color: var(--sl-color-primary-800);
  }

  .tag--primary:active > sl-icon-button {
    color: var(--sl-color-primary-600);
  }

  .tag--success {
    background-color: var(--sl-color-success-50);
    border-color: var(--sl-color-success-200);
    color: var(--sl-color-success-800);
  }

  .tag--success:active > sl-icon-button {
    color: var(--sl-color-success-600);
  }

  .tag--neutral {
    background-color: var(--sl-color-neutral-50);
    border-color: var(--sl-color-neutral-200);
    color: var(--sl-color-neutral-800);
  }

  .tag--neutral:active > sl-icon-button {
    color: var(--sl-color-neutral-600);
  }

  .tag--warning {
    background-color: var(--sl-color-warning-50);
    border-color: var(--sl-color-warning-200);
    color: var(--sl-color-warning-800);
  }

  .tag--warning:active > sl-icon-button {
    color: var(--sl-color-warning-600);
  }

  .tag--danger {
    background-color: var(--sl-color-danger-50);
    border-color: var(--sl-color-danger-200);
    color: var(--sl-color-danger-800);
  }

  .tag--danger:active > sl-icon-button {
    color: var(--sl-color-danger-600);
  }

  /*
   * Size modifiers
   */

  .tag--small {
    font-size: var(--sl-button-font-size-small);
    height: calc(var(--sl-input-height-small) * 0.8);
    line-height: calc(var(--sl-input-height-small) - var(--sl-input-border-width) * 2);
    border-radius: var(--sl-input-border-radius-small);
    padding: 0 var(--sl-spacing-x-small);
  }

  .tag--medium {
    font-size: var(--sl-button-font-size-medium);
    height: calc(var(--sl-input-height-medium) * 0.8);
    line-height: calc(var(--sl-input-height-medium) - var(--sl-input-border-width) * 2);
    border-radius: var(--sl-input-border-radius-medium);
    padding: 0 var(--sl-spacing-small);
  }

  .tag--large {
    font-size: var(--sl-button-font-size-large);
    height: calc(var(--sl-input-height-large) * 0.8);
    line-height: calc(var(--sl-input-height-large) - var(--sl-input-border-width) * 2);
    border-radius: var(--sl-input-border-radius-large);
    padding: 0 var(--sl-spacing-medium);
  }

  .tag__remove {
    margin-inline-start: var(--sl-spacing-x-small);
  }

  /*
   * Pill modifier
   */

  .tag--pill {
    border-radius: var(--sl-border-radius-pill);
  }
`});var Tr,Xo=f(()=>{T();Tr=z`
  :host {
    display: inline-block;
    color: var(--sl-color-neutral-600);
  }

  .icon-button {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    background: none;
    border: none;
    border-radius: var(--sl-border-radius-medium);
    font-size: inherit;
    color: inherit;
    padding: var(--sl-spacing-x-small);
    cursor: pointer;
    transition: var(--sl-transition-x-fast) color;
    -webkit-appearance: none;
  }

  .icon-button:hover:not(.icon-button--disabled),
  .icon-button:focus-visible:not(.icon-button--disabled) {
    color: var(--sl-color-primary-600);
  }

  .icon-button:active:not(.icon-button--disabled) {
    color: var(--sl-color-primary-700);
  }

  .icon-button:focus {
    outline: none;
  }

  .icon-button--disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .icon-button:focus-visible {
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  .icon-button__icon {
    pointer-events: none;
  }
`});var Lr,hl,Yo,Pr,Go,Rr,Sh,Ah,Vr=f(()=>{bt();Lr=Symbol.for(""),hl=t=>{if(t?.r===Lr)return t?._$litStatic$},Yo=(t,...e)=>({_$litStatic$:e.reduce((o,i,r)=>o+(s=>{if(s._$litStatic$!==void 0)return s._$litStatic$;throw Error(`Value passed to 'literal' function must be a 'literal' result: ${s}. Use 'unsafeStatic' to pass non-literal values, but
            take care to ensure page security.`)})(i)+t[r+1],t[0]),r:Lr}),Pr=new Map,Go=t=>(e,...o)=>{let i=o.length,r,s,l=[],h=[],c,p=0,u=!1;for(;p<i;){for(c=e[p];p<i&&(s=o[p],(r=hl(s))!==void 0);)c+=r+e[++p],u=!0;p!==i&&h.push(s),l.push(c),p++}if(p===i&&l.push(e[i]),u){let d=l.join("$$lit$$");(e=Pr.get(d))===void 0&&(l.raw=l,Pr.set(d,e=l)),o=h}return t(e,...o)},Rr=Go(x),Sh=Go(Ri),Ah=Go(Vi)});var Dr=f(()=>{Vr()});var Q,Zo=f(()=>{Xo();xt();H();N();M();dt();Dr();fe();et();Q=class extends L{constructor(){super(...arguments),this.hasFocus=!1,this.label="",this.disabled=!1}handleBlur(){this.hasFocus=!1,this.emit("sl-blur")}handleFocus(){this.hasFocus=!0,this.emit("sl-focus")}handleClick(t){this.disabled&&(t.preventDefault(),t.stopPropagation())}click(){this.button.click()}focus(t){this.button.focus(t)}blur(){this.button.blur()}render(){let t=!!this.href,e=t?Yo`a`:Yo`button`;return Rr`
      <${e}
        part="base"
        class=${R({"icon-button":!0,"icon-button--disabled":!t&&this.disabled,"icon-button--focused":this.hasFocus})}
        ?disabled=${y(t?void 0:this.disabled)}
        type=${y(t?void 0:"button")}
        href=${y(t?this.href:void 0)}
        target=${y(t?this.target:void 0)}
        download=${y(t?this.download:void 0)}
        rel=${y(t&&this.target?"noreferrer noopener":void 0)}
        role=${y(t?void 0:"button")}
        aria-disabled=${this.disabled?"true":"false"}
        aria-label="${this.label}"
        tabindex=${this.disabled?"-1":"0"}
        @blur=${this.handleBlur}
        @focus=${this.handleFocus}
        @click=${this.handleClick}
      >
        <sl-icon
          class="icon-button__icon"
          name=${y(this.name)}
          library=${y(this.library)}
          src=${y(this.src)}
          aria-hidden="true"
        ></sl-icon>
      </${e}>
    `}};Q.styles=[I,Tr];Q.dependencies={"sl-icon":q};n([P(".icon-button")],Q.prototype,"button",2);n([B()],Q.prototype,"hasFocus",2);n([a()],Q.prototype,"name",2);n([a()],Q.prototype,"library",2);n([a()],Q.prototype,"src",2);n([a()],Q.prototype,"href",2);n([a()],Q.prototype,"target",2);n([a()],Q.prototype,"download",2);n([a()],Q.prototype,"label",2);n([a({type:Boolean,reflect:!0})],Q.prototype,"disabled",2)});var Ht,Jo=f(()=>{Ko();Zo();ht();H();N();M();dt();T();et();Ht=class extends L{constructor(){super(...arguments),this.localize=new it(this),this.variant="neutral",this.size="medium",this.pill=!1,this.removable=!1}handleRemoveClick(){this.emit("sl-remove")}render(){return x`
      <span
        part="base"
        class=${R({tag:!0,"tag--primary":this.variant==="primary","tag--success":this.variant==="success","tag--neutral":this.variant==="neutral","tag--warning":this.variant==="warning","tag--danger":this.variant==="danger","tag--text":this.variant==="text","tag--small":this.size==="small","tag--medium":this.size==="medium","tag--large":this.size==="large","tag--pill":this.pill,"tag--removable":this.removable})}
      >
        <slot part="content" class="tag__content"></slot>

        ${this.removable?x`
              <sl-icon-button
                part="remove-button"
                exportparts="base:remove-button__base"
                name="x-lg"
                library="system"
                label=${this.localize.term("remove")}
                class="tag__remove"
                @click=${this.handleRemoveClick}
                tabindex="-1"
              ></sl-icon-button>
            `:""}
      </span>
    `}};Ht.styles=[I,Or];Ht.dependencies={"sl-icon-button":Q};n([a({reflect:!0})],Ht.prototype,"variant",2);n([a({reflect:!0})],Ht.prototype,"size",2);n([a({type:Boolean,reflect:!0})],Ht.prototype,"pill",2);n([a({type:Boolean})],Ht.prototype,"removable",2)});var Mr,Qo=f(()=>{T();Mr=z`
  :host {
    display: block;
  }

  /** The popup */
  .select {
    flex: 1 1 auto;
    display: inline-flex;
    width: 100%;
    position: relative;
    vertical-align: middle;
  }

  .select::part(popup) {
    z-index: var(--sl-z-index-dropdown);
  }

  .select[data-current-placement^='top']::part(popup) {
    transform-origin: bottom;
  }

  .select[data-current-placement^='bottom']::part(popup) {
    transform-origin: top;
  }

  /* Combobox */
  .select__combobox {
    flex: 1;
    display: flex;
    width: 100%;
    min-width: 0;
    position: relative;
    align-items: center;
    justify-content: start;
    font-family: var(--sl-input-font-family);
    font-weight: var(--sl-input-font-weight);
    letter-spacing: var(--sl-input-letter-spacing);
    vertical-align: middle;
    overflow: hidden;
    cursor: pointer;
    transition:
      var(--sl-transition-fast) color,
      var(--sl-transition-fast) border,
      var(--sl-transition-fast) box-shadow,
      var(--sl-transition-fast) background-color;
  }

  .select__display-input {
    position: relative;
    width: 100%;
    font: inherit;
    border: none;
    background: none;
    color: var(--sl-input-color);
    cursor: inherit;
    overflow: hidden;
    padding: 0;
    margin: 0;
    -webkit-appearance: none;
  }

  .select__display-input::placeholder {
    color: var(--sl-input-placeholder-color);
  }

  .select:not(.select--disabled):hover .select__display-input {
    color: var(--sl-input-color-hover);
  }

  .select__display-input:focus {
    outline: none;
  }

  /* Visually hide the display input when multiple is enabled */
  .select--multiple:not(.select--placeholder-visible) .select__display-input {
    position: absolute;
    z-index: -1;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
  }

  .select__value-input {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    padding: 0;
    margin: 0;
    opacity: 0;
    z-index: -1;
  }

  .select__tags {
    display: flex;
    flex: 1;
    align-items: center;
    flex-wrap: wrap;
    margin-inline-start: var(--sl-spacing-2x-small);
  }

  .select__tags::slotted(sl-tag) {
    cursor: pointer !important;
  }

  .select--disabled .select__tags,
  .select--disabled .select__tags::slotted(sl-tag) {
    cursor: not-allowed !important;
  }

  /* Standard selects */
  .select--standard .select__combobox {
    background-color: var(--sl-input-background-color);
    border: solid var(--sl-input-border-width) var(--sl-input-border-color);
  }

  .select--standard.select--disabled .select__combobox {
    background-color: var(--sl-input-background-color-disabled);
    border-color: var(--sl-input-border-color-disabled);
    color: var(--sl-input-color-disabled);
    opacity: 0.5;
    cursor: not-allowed;
    outline: none;
  }

  .select--standard:not(.select--disabled).select--open .select__combobox,
  .select--standard:not(.select--disabled).select--focused .select__combobox {
    background-color: var(--sl-input-background-color-focus);
    border-color: var(--sl-input-border-color-focus);
    box-shadow: 0 0 0 var(--sl-focus-ring-width) var(--sl-input-focus-ring-color);
  }

  /* Filled selects */
  .select--filled .select__combobox {
    border: none;
    background-color: var(--sl-input-filled-background-color);
    color: var(--sl-input-color);
  }

  .select--filled:hover:not(.select--disabled) .select__combobox {
    background-color: var(--sl-input-filled-background-color-hover);
  }

  .select--filled.select--disabled .select__combobox {
    background-color: var(--sl-input-filled-background-color-disabled);
    opacity: 0.5;
    cursor: not-allowed;
  }

  .select--filled:not(.select--disabled).select--open .select__combobox,
  .select--filled:not(.select--disabled).select--focused .select__combobox {
    background-color: var(--sl-input-filled-background-color-focus);
    outline: var(--sl-focus-ring);
  }

  /* Sizes */
  .select--small .select__combobox {
    border-radius: var(--sl-input-border-radius-small);
    font-size: var(--sl-input-font-size-small);
    min-height: var(--sl-input-height-small);
    padding-block: 0;
    padding-inline: var(--sl-input-spacing-small);
  }

  .select--small .select__clear {
    margin-inline-start: var(--sl-input-spacing-small);
  }

  .select--small .select__prefix::slotted(*) {
    margin-inline-end: var(--sl-input-spacing-small);
  }

  .select--small.select--multiple:not(.select--placeholder-visible) .select__prefix::slotted(*) {
    margin-inline-start: var(--sl-input-spacing-small);
  }

  .select--small.select--multiple:not(.select--placeholder-visible) .select__combobox {
    padding-block: 2px;
    padding-inline-start: 0;
  }

  .select--small .select__tags {
    gap: 2px;
  }

  .select--medium .select__combobox {
    border-radius: var(--sl-input-border-radius-medium);
    font-size: var(--sl-input-font-size-medium);
    min-height: var(--sl-input-height-medium);
    padding-block: 0;
    padding-inline: var(--sl-input-spacing-medium);
  }

  .select--medium .select__clear {
    margin-inline-start: var(--sl-input-spacing-medium);
  }

  .select--medium .select__prefix::slotted(*) {
    margin-inline-end: var(--sl-input-spacing-medium);
  }

  .select--medium.select--multiple:not(.select--placeholder-visible) .select__prefix::slotted(*) {
    margin-inline-start: var(--sl-input-spacing-medium);
  }

  .select--medium.select--multiple:not(.select--placeholder-visible) .select__combobox {
    padding-inline-start: 0;
    padding-block: 3px;
  }

  .select--medium .select__tags {
    gap: 3px;
  }

  .select--large .select__combobox {
    border-radius: var(--sl-input-border-radius-large);
    font-size: var(--sl-input-font-size-large);
    min-height: var(--sl-input-height-large);
    padding-block: 0;
    padding-inline: var(--sl-input-spacing-large);
  }

  .select--large .select__clear {
    margin-inline-start: var(--sl-input-spacing-large);
  }

  .select--large .select__prefix::slotted(*) {
    margin-inline-end: var(--sl-input-spacing-large);
  }

  .select--large.select--multiple:not(.select--placeholder-visible) .select__prefix::slotted(*) {
    margin-inline-start: var(--sl-input-spacing-large);
  }

  .select--large.select--multiple:not(.select--placeholder-visible) .select__combobox {
    padding-inline-start: 0;
    padding-block: 4px;
  }

  .select--large .select__tags {
    gap: 4px;
  }

  /* Pills */
  .select--pill.select--small .select__combobox {
    border-radius: var(--sl-input-height-small);
  }

  .select--pill.select--medium .select__combobox {
    border-radius: var(--sl-input-height-medium);
  }

  .select--pill.select--large .select__combobox {
    border-radius: var(--sl-input-height-large);
  }

  /* Prefix and Suffix */
  .select__prefix,
  .select__suffix {
    flex: 0;
    display: inline-flex;
    align-items: center;
    color: var(--sl-input-placeholder-color);
  }

  .select__suffix::slotted(*) {
    margin-inline-start: var(--sl-spacing-small);
  }

  /* Clear button */
  .select__clear {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: inherit;
    color: var(--sl-input-icon-color);
    border: none;
    background: none;
    padding: 0;
    transition: var(--sl-transition-fast) color;
    cursor: pointer;
  }

  .select__clear:hover {
    color: var(--sl-input-icon-color-hover);
  }

  .select__clear:focus {
    outline: none;
  }

  /* Expand icon */
  .select__expand-icon {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    transition: var(--sl-transition-medium) rotate ease;
    rotate: 0;
    margin-inline-start: var(--sl-spacing-small);
  }

  .select--open .select__expand-icon {
    rotate: -180deg;
  }

  /* Listbox */
  .select__listbox {
    display: block;
    position: relative;
    font-family: var(--sl-font-sans);
    font-size: var(--sl-font-size-medium);
    font-weight: var(--sl-font-weight-normal);
    box-shadow: var(--sl-shadow-large);
    background: var(--sl-panel-background-color);
    border: solid var(--sl-panel-border-width) var(--sl-panel-border-color);
    border-radius: var(--sl-border-radius-medium);
    padding-block: var(--sl-spacing-x-small);
    padding-inline: 0;
    overflow: auto;
    overscroll-behavior: none;

    /* Make sure it adheres to the popup's auto size */
    max-width: var(--auto-size-available-width);
    max-height: var(--auto-size-available-height);
  }

  .select__listbox ::slotted(sl-divider) {
    --spacing: var(--sl-spacing-x-small);
  }

  .select__listbox ::slotted(small) {
    display: block;
    font-size: var(--sl-font-size-small);
    font-weight: var(--sl-font-weight-semibold);
    color: var(--sl-color-neutral-500);
    padding-block: var(--sl-spacing-2x-small);
    padding-inline: var(--sl-spacing-x-large);
  }
`});function pl(t,e){return{top:Math.round(t.getBoundingClientRect().top-e.getBoundingClientRect().top),left:Math.round(t.getBoundingClientRect().left-e.getBoundingClientRect().left)}}function Br(t,e,o="vertical",i="smooth"){let r=pl(t,e),s=r.top+e.scrollTop,l=r.left+e.scrollLeft,h=e.scrollLeft,c=e.scrollLeft+e.offsetWidth,p=e.scrollTop,u=e.scrollTop+e.offsetHeight;(o==="horizontal"||o==="both")&&(l<h?e.scrollTo({left:l,behavior:i}):l+t.clientWidth>c&&e.scrollTo({left:l-e.offsetWidth+t.clientWidth,behavior:i})),(o==="vertical"||o==="both")&&(s<p?e.scrollTo({top:s,behavior:i}):s+t.clientHeight>u&&e.scrollTo({top:s-e.offsetHeight+t.clientHeight,behavior:i}))}var ti=f(()=>{});var Ir,mo=f(()=>{T();Ir=z`
  :host {
    --arrow-color: var(--sl-color-neutral-1000);
    --arrow-size: 6px;

    /*
     * These properties are computed to account for the arrow's dimensions after being rotated 45º. The constant
     * 0.7071 is derived from sin(45), which is the diagonal size of the arrow's container after rotating.
     */
    --arrow-size-diagonal: calc(var(--arrow-size) * 0.7071);
    --arrow-padding-offset: calc(var(--arrow-size-diagonal) - var(--arrow-size));

    display: contents;
  }

  .popup {
    position: absolute;
    isolation: isolate;
    max-width: var(--auto-size-available-width, none);
    max-height: var(--auto-size-available-height, none);
  }

  .popup--fixed {
    position: fixed;
  }

  .popup:not(.popup--active) {
    display: none;
  }

  .popup__arrow {
    position: absolute;
    width: calc(var(--arrow-size-diagonal) * 2);
    height: calc(var(--arrow-size-diagonal) * 2);
    rotate: 45deg;
    background: var(--arrow-color);
    z-index: -1;
  }

  /* Hover bridge */
  .popup-hover-bridge:not(.popup-hover-bridge--visible) {
    display: none;
  }

  .popup-hover-bridge {
    position: fixed;
    z-index: calc(var(--sl-z-index-dropdown) - 1);
    top: 0;
    right: 0;
    bottom: 0;
    left: 0;
    clip-path: polygon(
      var(--hover-bridge-top-left-x, 0) var(--hover-bridge-top-left-y, 0),
      var(--hover-bridge-top-right-x, 0) var(--hover-bridge-top-right-y, 0),
      var(--hover-bridge-bottom-right-x, 0) var(--hover-bridge-bottom-right-y, 0),
      var(--hover-bridge-bottom-left-x, 0) var(--hover-bridge-bottom-left-y, 0)
    );
  }
`});function ei(t,e,o){return ut(t,Ct(e,o))}function Jt(t,e){return typeof t=="function"?t(e):t}function Nt(t){return t.split("-")[0]}function Qt(t){return t.split("-")[1]}function oi(t){return t==="x"?"y":"x"}function vo(t){return t==="y"?"height":"width"}function $t(t){let e=t[0];return e==="t"||e==="b"?"y":"x"}function bo(t){return oi($t(t))}function Nr(t,e,o){o===void 0&&(o=!1);let i=Qt(t),r=bo(t),s=vo(r),l=r==="x"?i===(o?"end":"start")?"right":"left":i==="start"?"bottom":"top";return e.reference[s]>e.floating[s]&&(l=He(l)),[l,He(l)]}function Ur(t){let e=He(t);return[go(t),e,go(e)]}function go(t){return t.includes("start")?t.replace("start","end"):t.replace("end","start")}function ml(t,e,o){switch(t){case"top":case"bottom":return o?e?Hr:Fr:e?Fr:Hr;case"left":case"right":return e?ul:fl;default:return[]}}function qr(t,e,o,i){let r=Qt(t),s=ml(Nt(t),o==="start",i);return r&&(s=s.map(l=>l+"-"+r),e&&(s=s.concat(s.map(go)))),s}function He(t){let e=Nt(t);return dl[e]+t.slice(e.length)}function gl(t){var e,o,i,r;return{top:(e=t.top)!=null?e:0,right:(o=t.right)!=null?o:0,bottom:(i=t.bottom)!=null?i:0,left:(r=t.left)!=null?r:0}}function ii(t){return typeof t!="number"?gl(t):{top:t,right:t,bottom:t,left:t}}function te(t){let{x:e,y:o,width:i,height:r}=t;return{width:i,height:r,top:o,left:e,right:e+i,bottom:o+r,x:e,y:o}}var Ct,ut,Ne,Ue,kt,dl,Fr,Hr,ul,fl,yo=f(()=>{Ct=Math.min,ut=Math.max,Ne=Math.round,Ue=Math.floor,kt=t=>({x:t,y:t}),dl={left:"right",right:"left",bottom:"top",top:"bottom"};Fr=["left","right"],Hr=["right","left"],ul=["top","bottom"],fl=["bottom","top"]});function jr(t,e,o){let{reference:i,floating:r}=t,s=$t(e),l=bo(e),h=vo(l),c=Nt(e),p=s==="y",u=i.x+i.width/2-r.width/2,d=i.y+i.height/2-r.height/2,g=i[h]/2-r[h]/2,m;switch(c){case"top":m={x:u,y:i.y-r.height};break;case"bottom":m={x:u,y:i.y+i.height};break;case"right":m={x:i.x+i.width,y:d};break;case"left":m={x:i.x-r.width,y:d};break;default:m={x:i.x,y:i.y}}let v=Qt(e);return v&&(m[l]+=g*(v==="end"?1:-1)*(o&&p?-1:1)),m}async function Wr(t,e){var o;e===void 0&&(e={});let{x:i,y:r,platform:s,rects:l,elements:h,strategy:c}=t,{boundary:p="clippingAncestors",rootBoundary:u="viewport",elementContext:d="floating",altBoundary:g=!1,padding:m=0}=Jt(e,t),v=ii(m),k=h[g?d==="floating"?"reference":"floating":d],w=te(await s.getClippingRect({element:(o=await(s.isElement==null?void 0:s.isElement(k)))==null||o?k:k.contextElement||await(s.getDocumentElement==null?void 0:s.getDocumentElement(h.floating)),boundary:p,rootBoundary:u,strategy:c})),E=d==="floating"?{x:i,y:r,width:l.floating.width,height:l.floating.height}:l.reference,O=await(s.getOffsetParent==null?void 0:s.getOffsetParent(h.floating)),D=await(s.isElement==null?void 0:s.isElement(O))&&await(s.getScale==null?void 0:s.getScale(O))||{x:1,y:1},Z=te(s.convertOffsetParentRelativeRectToViewportRelativeRect?await s.convertOffsetParentRelativeRectToViewportRelativeRect({elements:h,rect:E,offsetParent:O,strategy:c}):E);return{top:(w.top-Z.top+v.top)/D.y,bottom:(Z.bottom-w.bottom+v.bottom)/D.y,left:(w.left-Z.left+v.left)/D.x,right:(Z.right-w.right+v.right)/D.x}}async function yl(t,e){let{placement:o,platform:i,elements:r}=t,s=await(i.isRTL==null?void 0:i.isRTL(r.floating)),l=Nt(o),h=Qt(o),c=$t(o)==="y",p=bl.has(l)?-1:1,u=s&&c?-1:1,d=Jt(e,t),{mainAxis:g,crossAxis:m,alignmentAxis:v}=typeof d=="number"?{mainAxis:d,crossAxis:0,alignmentAxis:null}:{mainAxis:d.mainAxis||0,crossAxis:d.crossAxis||0,alignmentAxis:d.alignmentAxis};return h&&typeof v=="number"&&(m=h==="end"?v*-1:v),c?{x:m*u,y:g*p}:{x:g*p,y:m*u}}var vl,Kr,Xr,Yr,bl,Gr,Zr,Jr,Qr=f(()=>{yo();yo();vl=50,Kr=async(t,e,o)=>{let{placement:i="bottom",strategy:r="absolute",middleware:s=[],platform:l}=o,h=l.detectOverflow?l:{...l,detectOverflow:Wr},c=await(l.isRTL==null?void 0:l.isRTL(e)),p=await l.getElementRects({reference:t,floating:e,strategy:r}),{x:u,y:d}=jr(p,i,c),g=i,m=0,v={};for(let _=0;_<s.length;_++){let k=s[_];if(!k)continue;let{name:w,fn:E}=k,{x:O,y:D,data:Z,reset:F}=await E({x:u,y:d,initialPlacement:i,placement:g,strategy:r,middlewareData:v,rects:p,platform:h,elements:{reference:t,floating:e}});u=O??u,d=D??d,v[w]={...v[w],...Z},F&&m<vl&&(m++,typeof F=="object"&&(F.placement&&(g=F.placement),F.rects&&(p=F.rects===!0?await l.getElementRects({reference:t,floating:e,strategy:r}):F.rects),{x:u,y:d}=jr(p,g,c)),_=-1)}return{x:u,y:d,placement:g,strategy:r,middlewareData:v}},Xr=t=>({name:"arrow",options:t,async fn(e){let{x:o,y:i,placement:r,rects:s,platform:l,elements:h,middlewareData:c}=e,{element:p,padding:u=0}=Jt(t,e)||{};if(p==null)return{};let d=ii(u),g={x:o,y:i},m=bo(r),v=vo(m),_=await l.getDimensions(p),k=m==="y",w=k?"top":"left",E=k?"bottom":"right",O=k?"clientHeight":"clientWidth",D=s.reference[v]+s.reference[m]-g[m]-s.floating[v],Z=g[m]-s.reference[m],F=await(l.getOffsetParent==null?void 0:l.getOffsetParent(p)),J=F?F[O]:0;(!J||!await(l.isElement==null?void 0:l.isElement(F)))&&(J=h.floating[O]||s.floating[v]);let rt=D/2-Z/2,gt=J/2-_[v]/2-1,K=Ct(d[w],gt),ke=Ct(d[E],gt),$e=J-_[v]-ke,vt=J/2-_[v]/2+rt,st=ei(K,vt,$e),qt=!c.arrow&&Qt(r)!=null&&vt!==st&&s.reference[v]/2-(vt<K?K:ke)-_[v]/2<0,At=qt?vt<K?vt-K:vt-$e:0;return{[m]:g[m]+At,data:{[m]:st,centerOffset:vt-st-At,...qt&&{alignmentOffset:At}},reset:qt}}}),Yr=function(t){return t===void 0&&(t={}),{name:"flip",options:t,async fn(e){var o,i;let{placement:r,middlewareData:s,rects:l,initialPlacement:h,platform:c,elements:p}=e,{mainAxis:u=!0,crossAxis:d=!0,fallbackPlacements:g,fallbackStrategy:m="bestFit",fallbackAxisSideDirection:v="none",flipAlignment:_=!0,...k}=Jt(t,e);if((o=s.arrow)!=null&&o.alignmentOffset)return{};let w=Nt(r),E=$t(h),O=Nt(h)===h,D=await(c.isRTL==null?void 0:c.isRTL(p.floating)),Z=g||(O||!_?[He(h)]:Ur(h)),F=v!=="none";!g&&F&&Z.push(...qr(h,_,v,D));let J=[h,...Z],rt=await c.detectOverflow(e,k),gt=[],K=((i=s.flip)==null?void 0:i.overflows)||[];if(u&&gt.push(rt[w]),d){let st=Nr(r,l,D);gt.push(rt[st[0]],rt[st[1]])}if(K=[...K,{placement:r,overflows:gt}],!gt.every(st=>st<=0)){var ke,$e;let st=(((ke=s.flip)==null?void 0:ke.index)||0)+1,qt=J[st];if(qt&&(!(d==="alignment"?E!==$t(qt):!1)||K.every(lt=>$t(lt.placement)===E?lt.overflows[0]>0:!0)))return{data:{index:st,overflows:K},reset:{placement:qt}};let At=($e=K.filter(jt=>jt.overflows[0]<=0).sort((jt,lt)=>jt.overflows[1]-lt.overflows[1])[0])==null?void 0:$e.placement;if(!At)switch(m){case"bestFit":{var vt;let jt=(vt=K.filter(lt=>{if(F){let Rt=$t(lt.placement);return Rt===E||Rt==="y"}return!0}).map(lt=>[lt.placement,lt.overflows.filter(Rt=>Rt>0).reduce((Rt,Fs)=>Rt+Fs,0)]).sort((lt,Rt)=>lt[1]-Rt[1])[0])==null?void 0:vt[0];jt&&(At=jt);break}case"initialPlacement":At=h;break}if(r!==At)return{reset:{placement:At}}}return{}}}},bl=new Set(["left","top"]);Gr=function(t){return t===void 0&&(t=0),{name:"offset",options:t,async fn(e){var o,i;let{x:r,y:s,placement:l,middlewareData:h}=e,c=await yl(e,t);return l===((o=h.offset)==null?void 0:o.placement)&&(i=h.arrow)!=null&&i.alignmentOffset?{}:{x:r+c.x,y:s+c.y,data:{...c,placement:l}}}}},Zr=function(t){return t===void 0&&(t={}),{name:"shift",options:t,async fn(e){let{x:o,y:i,placement:r,platform:s}=e,{mainAxis:l=!0,crossAxis:h=!1,limiter:c={fn:E=>{let{x:O,y:D}=E;return{x:O,y:D}}},...p}=Jt(t,e),u={x:o,y:i},d=await s.detectOverflow(e,p),g=$t(r),m=oi(g),v=u[m],_=u[g],k=(E,O)=>ei(O+d[E==="y"?"top":"left"],O,O-d[E==="y"?"bottom":"right"]);l&&(v=k(m,v)),h&&(_=k(g,_));let w=c.fn({...e,[m]:v,[g]:_});return{...w,data:{x:w.x-o,y:w.y-i,enabled:{[m]:l,[g]:h}}}}}},Jr=function(t){return t===void 0&&(t={}),{name:"size",options:t,async fn(e){let{placement:o,rects:i,platform:r,elements:s}=e,{apply:l=()=>{},...h}=Jt(t,e),c=await r.detectOverflow(e,h),p=Nt(o),u=Qt(o),d=$t(o)==="y",{width:g,height:m}=i.floating,v,_;p==="top"||p==="bottom"?(v=p,_=u===(await(r.isRTL==null?void 0:r.isRTL(s.floating))?"start":"end")?"left":"right"):(_=p,v=u==="end"?"top":"bottom");let k=m-c.top-c.bottom,w=g-c.left-c.right,E=Ct(m-c[v],k),O=Ct(g-c[_],w),D=e.middlewareData.shift,Z=!D,F=E,J=O;D!=null&&D.enabled.x&&(J=w),D!=null&&D.enabled.y&&(F=k),Z&&!u&&(d?J=g-2*ut(c.left,c.right):F=m-2*ut(c.top,c.bottom)),await l({...e,availableWidth:J,availableHeight:F});let rt=await r.getDimensions(s.floating);return g!==rt.width||m!==rt.height?{reset:{rects:!0}}:{}}}}});function _o(){return typeof window<"u"}function oe(t){return es(t)?(t.nodeName||"").toLowerCase():"#document"}function G(t){var e;return(t==null||(e=t.ownerDocument)==null?void 0:e.defaultView)||window}function St(t){var e;return(e=(es(t)?t.ownerDocument:t.document)||window.document)==null?void 0:e.documentElement}function es(t){return _o()?t instanceof Node||t instanceof G(t).Node:!1}function ft(t){return _o()?t instanceof Element||t instanceof G(t).Element:!1}function Lt(t){return _o()?t instanceof HTMLElement||t instanceof G(t).HTMLElement:!1}function ts(t){return!_o()||typeof ShadowRoot>"u"?!1:t instanceof ShadowRoot||t instanceof G(t).ShadowRoot}function qe(t){let{overflow:e,overflowX:o,overflowY:i,display:r}=mt(t);return/auto|scroll|overlay|hidden|clip/.test(e+i+o)&&r!=="inline"&&r!=="contents"}function os(t){return/^(table|td|th)$/.test(oe(t))}function je(t){try{if(t.matches(":popover-open"))return!0}catch{}try{return t.matches(":modal")}catch{return!1}}function ge(t){let e=ft(t)?mt(t):t;return ee(e.transform)||ee(e.translate)||ee(e.scale)||ee(e.rotate)||ee(e.perspective)||!wo()&&(ee(e.backdropFilter)||ee(e.filter))||_l.test(e.willChange||"")||wl.test(e.contain||"")}function is(t){let e=Ut(t);for(;Lt(e)&&!ve(e);){if(ge(e))return e;if(je(e))return null;e=Ut(e)}return null}function wo(){return ri==null&&(ri=typeof CSS<"u"&&CSS.supports&&CSS.supports("-webkit-backdrop-filter","none")),ri}function ve(t){return/^(html|body|#document)$/.test(oe(t))}function mt(t){return G(t).getComputedStyle(t)}function We(t){return ft(t)?{scrollLeft:t.scrollLeft,scrollTop:t.scrollTop}:{scrollLeft:t.scrollX,scrollTop:t.scrollY}}function Ut(t){if(oe(t)==="html")return t;let e=t.assignedSlot||t.parentNode||ts(t)&&t.host||St(t);return ts(e)?e.host:e}function rs(t){let e=Ut(t);return ve(e)?(t.ownerDocument||t).body:Lt(e)&&qe(e)?e:rs(e)}function me(t,e,o){var i;e===void 0&&(e=[]),o===void 0&&(o=!0);let r=rs(t),s=r===((i=t.ownerDocument)==null?void 0:i.body),l=G(r);if(s){let h=xo(l);return e.concat(l,l.visualViewport||[],qe(r)?r:[],h&&o?me(h):[])}else return e.concat(r,me(r,[],o))}function xo(t){return t.parent&&Object.getPrototypeOf(t.parent)?t.frameElement:null}var _l,wl,ee,ri,si=f(()=>{_l=/transform|translate|scale|rotate|perspective|filter/,wl=/paint|layout|strict|content/,ee=t=>!!t&&t!=="none"});function ns(t){let e=mt(t),o=parseFloat(e.width)||0,i=parseFloat(e.height)||0,r=Lt(t),s=r?t.offsetWidth:o,l=r?t.offsetHeight:i,h=Ne(o)!==s||Ne(i)!==l;return h&&(o=s,i=l),{width:o,height:i,$:h}}function ni(t){return ft(t)?t:t.contextElement}function be(t){let e=ni(t);if(!Lt(e))return kt(1);let o=e.getBoundingClientRect(),{width:i,height:r,$:s}=ns(e),l=(s?Ne(o.width):o.width)/i,h=(s?Ne(o.height):o.height)/r;return(!l||!Number.isFinite(l))&&(l=1),(!h||!Number.isFinite(h))&&(h=1),{x:l,y:h}}function as(t){let e=G(t);return!wo()||!e.visualViewport?xl:{x:e.visualViewport.offsetLeft,y:e.visualViewport.offsetTop}}function Cl(t,e,o){return e===void 0&&(e=!1),!!o&&e&&o===G(t)}function ie(t,e,o,i){e===void 0&&(e=!1),o===void 0&&(o=!1);let r=t.getBoundingClientRect(),s=ni(t),l=kt(1);e&&(i?ft(i)&&(l=be(i)):l=be(t));let h=Cl(s,o,i)?as(s):kt(0),c=(r.left+h.x)/l.x,p=(r.top+h.y)/l.y,u=r.width/l.x,d=r.height/l.y;if(s&&i){let g=G(s),m=ft(i)?G(i):i,v=g,_=xo(v);for(;_&&m!==v;){let k=be(_),w=_.getBoundingClientRect(),E=mt(_),O=w.left+(_.clientLeft+parseFloat(E.paddingLeft))*k.x,D=w.top+(_.clientTop+parseFloat(E.paddingTop))*k.y;c*=k.x,p*=k.y,u*=k.x,d*=k.y,c+=O,p+=D,v=G(_),_=xo(v)}}return te({width:u,height:d,x:c,y:p})}function Co(t,e){let o=We(t).scrollLeft;return e?e.left+o:ie(St(t)).left+o}function cs(t,e){let o=t.getBoundingClientRect(),i=o.left+e.scrollLeft-Co(t,o),r=o.top+e.scrollTop;return{x:i,y:r}}function kl(t){let{elements:e,rect:o,offsetParent:i,strategy:r}=t,s=r==="fixed",l=St(i),h=e?je(e.floating):!1;if(i===l||h&&s)return o;let c={scrollLeft:0,scrollTop:0},p=kt(1),u=kt(0),d=Lt(i);if((d||!s)&&((oe(i)!=="body"||qe(l))&&(c=We(i)),d)){let m=ie(i);p=be(i),u.x=m.x+i.clientLeft,u.y=m.y+i.clientTop}let g=l&&!d&&!s?cs(l,c):kt(0);return{width:o.width*p.x,height:o.height*p.y,x:o.x*p.x-c.scrollLeft*p.x+u.x+g.x,y:o.y*p.y-c.scrollTop*p.y+u.y+g.y}}function $l(t){return t.getClientRects?Array.from(t.getClientRects()):[]}function Sl(t){let e=We(t),o=t.ownerDocument.body,i=ut(t.scrollWidth,t.clientWidth,o.scrollWidth,o.clientWidth),r=ut(t.scrollHeight,t.clientHeight,o.scrollHeight,o.clientHeight),s=-e.scrollLeft+Co(t),l=-e.scrollTop;return mt(o).direction==="rtl"&&(s+=ut(t.clientWidth,o.clientWidth)-i),{width:i,height:r,x:s,y:l}}function El(t,e,o){o===void 0&&(o="viewport");let i=o==="layoutViewport",r=G(t),s=St(t),l=r.visualViewport,h=s.clientWidth,c=s.clientHeight,p=0,u=0;if(l){let g=!wo()||e==="fixed";i?g||(p=-l.offsetLeft,u=-l.offsetTop):(h=l.width,c=l.height,g&&(p=l.offsetLeft,u=l.offsetTop))}if(Co(s)<=0){let g=s.ownerDocument,m=g.body,v=getComputedStyle(m),_=g.compatMode==="CSS1Compat"&&parseFloat(v.marginLeft)+parseFloat(v.marginRight)||0,k=Math.abs(s.clientWidth-m.clientWidth-_),w=getComputedStyle(s).scrollbarGutter==="stable both-edges"?k/2:k;w<=Al&&(h-=w)}return{width:h,height:c,x:p,y:u}}function zl(t,e){let o=ie(t,!0,e==="fixed"),i=o.top+t.clientTop,r=o.left+t.clientLeft,s=be(t),l=t.clientWidth*s.x,h=t.clientHeight*s.y,c=r*s.x,p=i*s.y;return{width:l,height:h,x:c,y:p}}function ss(t,e,o){let i;if(e==="viewport"||e==="layoutViewport")i=El(t,o,e);else if(e==="document")i=Sl(St(t));else if(ft(e))i=zl(e,o);else{let r=as(t);i={x:e.x-r.x,y:e.y-r.y,width:e.width,height:e.height}}return te(i)}function Ol(t,e){let o=e.get(t);if(o)return o;let i=me(t,[],!1).filter(h=>ft(h)&&oe(h)!=="body"),r=null,s=mt(t).position==="fixed",l=s?Ut(t):t;for(;ft(l)&&!ve(l);){let h=mt(l),c=ge(l),p=r?r.position:s?"fixed":"";!c&&(p==="fixed"||p==="absolute"&&h.position==="static")?i=i.filter(d=>d!==l):r=h,l=Ut(l)}return e.set(t,i),i}function Tl(t){let{element:e,boundary:o,rootBoundary:i,strategy:r}=t,l=[...o==="clippingAncestors"?je(e)?[]:Ol(e,this._c):[].concat(o),i],h=ss(e,l[0],r),c=h.top,p=h.right,u=h.bottom,d=h.left;for(let g=1;g<l.length;g++){let m=ss(e,l[g],r);c=ut(m.top,c),p=Ct(m.right,p),u=Ct(m.bottom,u),d=ut(m.left,d)}return{width:p-d,height:u-c,x:d,y:c}}function Pl(t){let{width:e,height:o}=ns(t);return{width:e,height:o}}function Ll(t,e,o){let i=Lt(e),r=St(e),s=o==="fixed",l=ie(t,!0,s,e),h={scrollLeft:0,scrollTop:0},c=kt(0);if((i||!s)&&((oe(e)!=="body"||qe(r))&&(h=We(e)),i)){let g=ie(e,!0,s,e);c.x=g.x+e.clientLeft,c.y=g.y+e.clientTop}!i&&r&&(c.x=Co(r));let p=r&&!i&&!s?cs(r,h):kt(0),u=l.left+h.scrollLeft-c.x-p.x,d=l.top+h.scrollTop-c.y-p.y;return{x:u,y:d,width:l.width,height:l.height}}function li(t){return mt(t).position==="static"}function ls(t,e){if(!Lt(t)||mt(t).position==="fixed")return null;if(e)return e(t);let o=t.offsetParent;return St(t)===o&&(o=o.ownerDocument.body),o}function hs(t,e){let o=G(t);if(je(t))return o;if(!Lt(t)){let r=Ut(t);for(;r&&!ve(r);){if(ft(r)&&!li(r))return r;r=Ut(r)}return o}let i=ls(t,e);for(;i&&os(i)&&li(i);)i=ls(i,e);return i&&ve(i)&&li(i)&&!ge(i)?o:i||is(t)||o}function Vl(t){return mt(t).direction==="rtl"}function ps(t,e){return t.x===e.x&&t.y===e.y&&t.width===e.width&&t.height===e.height}function Dl(t,e,o){let i=null,r,s=St(t);function l(){var u;clearTimeout(r),(u=i)==null||u.disconnect(),i=null}function h(u,d){u===void 0&&(u=!1),d===void 0&&(d=1),l();let g=t.getBoundingClientRect(),{left:m,top:v,width:_,height:k}=g;if(u||e(),!_||!k)return;let w=Ue(v),E=Ue(s.clientWidth-(m+_)),O=Ue(s.clientHeight-(v+k)),D=Ue(m),F={rootMargin:-w+"px "+-E+"px "+-O+"px "+-D+"px",threshold:ut(0,Ct(1,d))||1},J=!0;function rt(gt){let K=gt[0].intersectionRatio;if(!ps(g,t.getBoundingClientRect()))return h();if(K!==d){if(!J)return h();K?h(!1,K):r=setTimeout(()=>{h(!1,1e-7)},1e3)}J=!1}try{i=new IntersectionObserver(rt,{...F,root:s.ownerDocument})}catch{i=new IntersectionObserver(rt,F)}i.observe(t)}let c=G(t),p=()=>h(o);return c.addEventListener("resize",p),h(!0),()=>{c.removeEventListener("resize",p),l()}}function ds(t,e,o,i){i===void 0&&(i={});let{ancestorScroll:r=!0,ancestorResize:s=!0,elementResize:l=typeof ResizeObserver=="function",layoutShift:h=typeof IntersectionObserver=="function",animationFrame:c=!1}=i,p=ni(t),u=r||s?[...p?me(p):[],...e?me(e):[]]:[];u.forEach(w=>{r&&w.addEventListener("scroll",o),s&&w.addEventListener("resize",o)});let d=p&&h?Dl(p,o,s):null,g=-1,m=null;l&&(m=new ResizeObserver(w=>{let[E]=w;E&&E.target===p&&m&&e&&(m.unobserve(e),cancelAnimationFrame(g),g=requestAnimationFrame(()=>{var O;(O=m)==null||O.observe(e)})),o()}),p&&!c&&m.observe(p),e&&m.observe(e));let v,_=c?ie(t):null;c&&k();function k(){let w=ie(t);_&&!ps(_,w)&&o(),_=w,v=requestAnimationFrame(k)}return o(),()=>{var w;u.forEach(E=>{r&&E.removeEventListener("scroll",o),s&&E.removeEventListener("resize",o)}),d?.(),(w=m)==null||w.disconnect(),m=null,c&&cancelAnimationFrame(v)}}var xl,Al,Rl,Ke,us,fs,ms,ai,gs,vs,bs=f(()=>{Qr();yo();si();xl=kt(0);Al=25;Rl=async function(t){let e=this.getOffsetParent||hs,o=this.getDimensions,i=await o(t.floating);return{reference:Ll(t.reference,await e(t.floating),t.strategy),floating:{x:0,y:0,width:i.width,height:i.height}}};Ke={convertOffsetParentRelativeRectToViewportRelativeRect:kl,getDocumentElement:St,getClippingRect:Tl,getOffsetParent:hs,getElementRects:Rl,getClientRects:$l,getDimensions:Pl,getScale:be,isElement:ft,isRTL:Vl};us=Gr,fs=Zr,ms=Yr,ai=Jr,gs=Xr,vs=(t,e,o)=>{let i=new Map,r=o??{},s={...Ke,...r.platform,_c:i};return Kr(t,e,{...r,platform:s})}});function ys(t){return Ml(t)}function ci(t){return t.assignedSlot?t.assignedSlot:t.parentNode instanceof ShadowRoot?t.parentNode.host:t.parentNode}function Ml(t){for(let e=t;e;e=ci(e))if(e instanceof Element&&getComputedStyle(e).display==="none")return null;for(let e=ci(t);e;e=ci(e)){if(!(e instanceof Element))continue;let o=getComputedStyle(e);if(o.display!=="contents"&&(o.position!=="static"||ge(o)||e.tagName==="BODY"))return e}return null}var _s=f(()=>{si()});function Bl(t){return t!==null&&typeof t=="object"&&"getBoundingClientRect"in t&&("contextElement"in t?t.contextElement instanceof Element:!0)}var A,Xe=f(()=>{mo();ht();H();N();M();bs();dt();T();_s();et();A=class extends L{constructor(){super(...arguments),this.localize=new it(this),this.active=!1,this.placement="top",this.strategy="absolute",this.distance=0,this.skidding=0,this.arrow=!1,this.arrowPlacement="anchor",this.arrowPadding=10,this.flip=!1,this.flipFallbackPlacements="",this.flipFallbackStrategy="best-fit",this.flipPadding=0,this.shift=!1,this.shiftPadding=0,this.autoSizePadding=0,this.hoverBridge=!1,this.updateHoverBridge=()=>{if(this.hoverBridge&&this.anchorEl){let t=this.anchorEl.getBoundingClientRect(),e=this.popup.getBoundingClientRect(),o=this.placement.includes("top")||this.placement.includes("bottom"),i=0,r=0,s=0,l=0,h=0,c=0,p=0,u=0;o?t.top<e.top?(i=t.left,r=t.bottom,s=t.right,l=t.bottom,h=e.left,c=e.top,p=e.right,u=e.top):(i=e.left,r=e.bottom,s=e.right,l=e.bottom,h=t.left,c=t.top,p=t.right,u=t.top):t.left<e.left?(i=t.right,r=t.top,s=e.left,l=e.top,h=t.right,c=t.bottom,p=e.left,u=e.bottom):(i=e.right,r=e.top,s=t.left,l=t.top,h=e.right,c=e.bottom,p=t.left,u=t.bottom),this.style.setProperty("--hover-bridge-top-left-x",`${i}px`),this.style.setProperty("--hover-bridge-top-left-y",`${r}px`),this.style.setProperty("--hover-bridge-top-right-x",`${s}px`),this.style.setProperty("--hover-bridge-top-right-y",`${l}px`),this.style.setProperty("--hover-bridge-bottom-left-x",`${h}px`),this.style.setProperty("--hover-bridge-bottom-left-y",`${c}px`),this.style.setProperty("--hover-bridge-bottom-right-x",`${p}px`),this.style.setProperty("--hover-bridge-bottom-right-y",`${u}px`)}}}async connectedCallback(){super.connectedCallback(),await this.updateComplete,this.start()}disconnectedCallback(){super.disconnectedCallback(),this.stop()}async updated(t){super.updated(t),t.has("active")&&(this.active?this.start():this.stop()),t.has("anchor")&&this.handleAnchorChange(),this.active&&(await this.updateComplete,this.reposition())}async handleAnchorChange(){if(await this.stop(),this.anchor&&typeof this.anchor=="string"){let t=this.getRootNode();this.anchorEl=t.getElementById(this.anchor)}else this.anchor instanceof Element||Bl(this.anchor)?this.anchorEl=this.anchor:this.anchorEl=this.querySelector('[slot="anchor"]');this.anchorEl instanceof HTMLSlotElement&&(this.anchorEl=this.anchorEl.assignedElements({flatten:!0})[0]),this.anchorEl&&this.active&&this.start()}start(){!this.anchorEl||!this.active||(this.cleanup=ds(this.anchorEl,this.popup,()=>{this.reposition()}))}async stop(){return new Promise(t=>{this.cleanup?(this.cleanup(),this.cleanup=void 0,this.removeAttribute("data-current-placement"),this.style.removeProperty("--auto-size-available-width"),this.style.removeProperty("--auto-size-available-height"),requestAnimationFrame(()=>t())):t()})}reposition(){if(!this.active||!this.anchorEl)return;let t=[us({mainAxis:this.distance,crossAxis:this.skidding})];this.sync?t.push(ai({apply:({rects:o})=>{let i=this.sync==="width"||this.sync==="both",r=this.sync==="height"||this.sync==="both";this.popup.style.width=i?`${o.reference.width}px`:"",this.popup.style.height=r?`${o.reference.height}px`:""}})):(this.popup.style.width="",this.popup.style.height=""),this.flip&&t.push(ms({boundary:this.flipBoundary,fallbackPlacements:this.flipFallbackPlacements,fallbackStrategy:this.flipFallbackStrategy==="best-fit"?"bestFit":"initialPlacement",padding:this.flipPadding})),this.shift&&t.push(fs({boundary:this.shiftBoundary,padding:this.shiftPadding})),this.autoSize?t.push(ai({boundary:this.autoSizeBoundary,padding:this.autoSizePadding,apply:({availableWidth:o,availableHeight:i})=>{this.autoSize==="vertical"||this.autoSize==="both"?this.style.setProperty("--auto-size-available-height",`${i}px`):this.style.removeProperty("--auto-size-available-height"),this.autoSize==="horizontal"||this.autoSize==="both"?this.style.setProperty("--auto-size-available-width",`${o}px`):this.style.removeProperty("--auto-size-available-width")}})):(this.style.removeProperty("--auto-size-available-width"),this.style.removeProperty("--auto-size-available-height")),this.arrow&&t.push(gs({element:this.arrowEl,padding:this.arrowPadding}));let e=this.strategy==="absolute"?o=>Ke.getOffsetParent(o,ys):Ke.getOffsetParent;vs(this.anchorEl,this.popup,{placement:this.placement,middleware:t,strategy:this.strategy,platform:It(tt({},Ke),{getOffsetParent:e})}).then(({x:o,y:i,middlewareData:r,placement:s})=>{let l=this.localize.dir()==="rtl",h={top:"bottom",right:"left",bottom:"top",left:"right"}[s.split("-")[0]];if(this.setAttribute("data-current-placement",s),Object.assign(this.popup.style,{left:`${o}px`,top:`${i}px`}),this.arrow){let c=r.arrow.x,p=r.arrow.y,u="",d="",g="",m="";if(this.arrowPlacement==="start"){let v=typeof c=="number"?`calc(${this.arrowPadding}px - var(--arrow-padding-offset))`:"";u=typeof p=="number"?`calc(${this.arrowPadding}px - var(--arrow-padding-offset))`:"",d=l?v:"",m=l?"":v}else if(this.arrowPlacement==="end"){let v=typeof c=="number"?`calc(${this.arrowPadding}px - var(--arrow-padding-offset))`:"";d=l?"":v,m=l?v:"",g=typeof p=="number"?`calc(${this.arrowPadding}px - var(--arrow-padding-offset))`:""}else this.arrowPlacement==="center"?(m=typeof c=="number"?"calc(50% - var(--arrow-size-diagonal))":"",u=typeof p=="number"?"calc(50% - var(--arrow-size-diagonal))":""):(m=typeof c=="number"?`${c}px`:"",u=typeof p=="number"?`${p}px`:"");Object.assign(this.arrowEl.style,{top:u,right:d,bottom:g,left:m,[h]:"calc(var(--arrow-size-diagonal) * -1)"})}}),requestAnimationFrame(()=>this.updateHoverBridge()),this.emit("sl-reposition")}render(){return x`
      <slot name="anchor" @slotchange=${this.handleAnchorChange}></slot>

      <span
        part="hover-bridge"
        class=${R({"popup-hover-bridge":!0,"popup-hover-bridge--visible":this.hoverBridge&&this.active})}
      ></span>

      <div
        part="popup"
        class=${R({popup:!0,"popup--active":this.active,"popup--fixed":this.strategy==="fixed","popup--has-arrow":this.arrow})}
      >
        <slot></slot>
        ${this.arrow?x`<div part="arrow" class="popup__arrow" role="presentation"></div>`:""}
      </div>
    `}};A.styles=[I,Ir];n([P(".popup")],A.prototype,"popup",2);n([P(".popup__arrow")],A.prototype,"arrowEl",2);n([a()],A.prototype,"anchor",2);n([a({type:Boolean,reflect:!0})],A.prototype,"active",2);n([a({reflect:!0})],A.prototype,"placement",2);n([a({reflect:!0})],A.prototype,"strategy",2);n([a({type:Number})],A.prototype,"distance",2);n([a({type:Number})],A.prototype,"skidding",2);n([a({type:Boolean})],A.prototype,"arrow",2);n([a({attribute:"arrow-placement"})],A.prototype,"arrowPlacement",2);n([a({attribute:"arrow-padding",type:Number})],A.prototype,"arrowPadding",2);n([a({type:Boolean})],A.prototype,"flip",2);n([a({attribute:"flip-fallback-placements",converter:{fromAttribute:t=>t.split(" ").map(e=>e.trim()).filter(e=>e!==""),toAttribute:t=>t.join(" ")}})],A.prototype,"flipFallbackPlacements",2);n([a({attribute:"flip-fallback-strategy"})],A.prototype,"flipFallbackStrategy",2);n([a({type:Object})],A.prototype,"flipBoundary",2);n([a({attribute:"flip-padding",type:Number})],A.prototype,"flipPadding",2);n([a({type:Boolean})],A.prototype,"shift",2);n([a({type:Object})],A.prototype,"shiftBoundary",2);n([a({attribute:"shift-padding",type:Number})],A.prototype,"shiftPadding",2);n([a({attribute:"auto-size"})],A.prototype,"autoSize",2);n([a()],A.prototype,"sync",2);n([a({type:Object})],A.prototype,"autoSizeBoundary",2);n([a({attribute:"auto-size-padding",type:Number})],A.prototype,"autoSizePadding",2);n([a({attribute:"hover-bridge",type:Boolean})],A.prototype,"hoverBridge",2)});function Fl(t){return t??{keyframes:[],options:{duration:0}}}function ws(t,e){return e.toLowerCase()==="rtl"?{keyframes:t.rtlKeyframes||t.keyframes,options:t.options}:t}function ye(t,e){xs.set(t,Fl(e))}function _e(t,e,o){let i=Il.get(t);if(i?.[e])return ws(i[e],o.dir);let r=xs.get(e);return r?ws(r,o.dir):{keyframes:[],options:{duration:0}}}var xs,Il,Ye=f(()=>{M();xs=new Map,Il=new WeakMap});function we(t,e){return new Promise(o=>{function i(r){r.target===t&&(t.removeEventListener(e,i),o())}t.addEventListener(e,i)})}var Ge=f(()=>{});function xe(t,e,o){return new Promise(i=>{if(o?.duration===1/0)throw new Error("Promise-based animations must be finite.");let r=t.animate(e,It(tt({},o),{duration:Hl()?0:o.duration}));r.addEventListener("cancel",i,{once:!0}),r.addEventListener("finish",i,{once:!0})})}function hi(t){return t=t.toString().toLowerCase(),t.indexOf("ms")>-1?parseFloat(t):t.indexOf("s")>-1?parseFloat(t)*1e3:parseFloat(t)}function Hl(){return window.matchMedia("(prefers-reduced-motion: reduce)").matches}function Ce(t){return Promise.all(t.getAnimations().map(e=>new Promise(o=>{e.cancel(),requestAnimationFrame(o)})))}var Ze=f(()=>{M()});var Je,Cs,ks=f(()=>{bt();fo();Je=class extends Ft{constructor(e){if(super(e),this.it=V,e.type!==pt.CHILD)throw Error(this.constructor.directiveName+"() can only be used in child bindings")}render(e){if(e===V||e==null)return this._t=void 0,this.it=e;if(e===X)return e;if(typeof e!="string")throw Error(this.constructor.directiveName+"() called with a non-string value");if(e===this.it)return this._t;this.it=e;let o=[e];return o.raw=o,this._t={_$litType$:this.constructor.resultType,strings:o,values:[]}}};Je.directiveName="unsafeHTML",Je.resultType=1;Cs=ue(Je)});var $s=f(()=>{ks()});var C,pi=f(()=>{Jo();Qo();ti();nt();Xe();at();Ye();Ge();Ze();ct();ht();xt();Y();H();N();M();dt();T();et();$s();C=class extends L{constructor(){super(...arguments),this.formControlController=new _t(this,{assumeInteractionOn:["sl-blur","sl-input"]}),this.hasSlotController=new wt(this,"help-text","label"),this.localize=new it(this),this.typeToSelectString="",this.hasFocus=!1,this.displayLabel="",this.selectedOptions=[],this.valueHasChanged=!1,this.name="",this._value="",this.defaultValue="",this.size="medium",this.placeholder="",this.multiple=!1,this.maxOptionsVisible=3,this.disabled=!1,this.clearable=!1,this.open=!1,this.hoist=!1,this.filled=!1,this.pill=!1,this.label="",this.placement="bottom",this.helpText="",this.form="",this.required=!1,this.getTag=t=>x`
      <sl-tag
        part="tag"
        exportparts="
              base:tag__base,
              content:tag__content,
              remove-button:tag__remove-button,
              remove-button__base:tag__remove-button__base
            "
        ?pill=${this.pill}
        size=${this.size}
        removable
        @sl-remove=${e=>this.handleTagRemove(e,t)}
      >
        ${t.getTextLabel()}
      </sl-tag>
    `,this.handleDocumentFocusIn=t=>{let e=t.composedPath();this&&!e.includes(this)&&this.hide()},this.handleDocumentKeyDown=t=>{let e=t.target,o=e.closest(".select__clear")!==null,i=e.closest("sl-icon-button")!==null;if(!(o||i)){if(t.key==="Escape"&&this.open&&!this.closeWatcher&&(t.preventDefault(),t.stopPropagation(),this.hide(),this.displayInput.focus({preventScroll:!0})),t.key==="Enter"||t.key===" "&&this.typeToSelectString===""){if(t.preventDefault(),t.stopImmediatePropagation(),!this.open){this.show();return}this.currentOption&&!this.currentOption.disabled&&(this.valueHasChanged=!0,this.multiple?this.toggleOptionSelection(this.currentOption):this.setSelectedOptions(this.currentOption),this.updateComplete.then(()=>{this.emit("sl-input"),this.emit("sl-change")}),this.multiple||(this.hide(),this.displayInput.focus({preventScroll:!0})));return}if(["ArrowUp","ArrowDown","Home","End"].includes(t.key)){let r=this.getAllOptions(),s=r.indexOf(this.currentOption),l=Math.max(0,s);if(t.preventDefault(),!this.open&&(this.show(),this.currentOption))return;t.key==="ArrowDown"?(l=s+1,l>r.length-1&&(l=0)):t.key==="ArrowUp"?(l=s-1,l<0&&(l=r.length-1)):t.key==="Home"?l=0:t.key==="End"&&(l=r.length-1),this.setCurrentOption(r[l])}if(t.key&&t.key.length===1||t.key==="Backspace"){let r=this.getAllOptions();if(t.metaKey||t.ctrlKey||t.altKey)return;if(!this.open){if(t.key==="Backspace")return;this.show()}t.stopPropagation(),t.preventDefault(),clearTimeout(this.typeToSelectTimeout),this.typeToSelectTimeout=window.setTimeout(()=>this.typeToSelectString="",1e3),t.key==="Backspace"?this.typeToSelectString=this.typeToSelectString.slice(0,-1):this.typeToSelectString+=t.key.toLowerCase();for(let s of r)if(s.getTextLabel().toLowerCase().startsWith(this.typeToSelectString)){this.setCurrentOption(s);break}}}},this.handleDocumentMouseDown=t=>{let e=t.composedPath();this&&!e.includes(this)&&this.hide()}}get value(){return this._value}set value(t){this.multiple?t=Array.isArray(t)?t:t.split(" "):t=Array.isArray(t)?t.join(" "):t,this._value!==t&&(this.valueHasChanged=!0,this._value=t)}get validity(){return this.valueInput.validity}get validationMessage(){return this.valueInput.validationMessage}connectedCallback(){super.connectedCallback(),setTimeout(()=>{this.handleDefaultSlotChange()}),this.open=!1}addOpenListeners(){var t;document.addEventListener("focusin",this.handleDocumentFocusIn),document.addEventListener("keydown",this.handleDocumentKeyDown),document.addEventListener("mousedown",this.handleDocumentMouseDown),this.getRootNode()!==document&&this.getRootNode().addEventListener("focusin",this.handleDocumentFocusIn),"CloseWatcher"in window&&((t=this.closeWatcher)==null||t.destroy(),this.closeWatcher=new CloseWatcher,this.closeWatcher.onclose=()=>{this.open&&(this.hide(),this.displayInput.focus({preventScroll:!0}))})}removeOpenListeners(){var t;document.removeEventListener("focusin",this.handleDocumentFocusIn),document.removeEventListener("keydown",this.handleDocumentKeyDown),document.removeEventListener("mousedown",this.handleDocumentMouseDown),this.getRootNode()!==document&&this.getRootNode().removeEventListener("focusin",this.handleDocumentFocusIn),(t=this.closeWatcher)==null||t.destroy()}handleFocus(){this.hasFocus=!0,this.displayInput.setSelectionRange(0,0),this.emit("sl-focus")}handleBlur(){this.hasFocus=!1,this.emit("sl-blur")}handleLabelClick(){this.displayInput.focus()}handleComboboxMouseDown(t){let o=t.composedPath().some(i=>i instanceof Element&&i.tagName.toLowerCase()==="sl-icon-button");this.disabled||o||(t.preventDefault(),this.displayInput.focus({preventScroll:!0}),this.open=!this.open)}handleComboboxKeyDown(t){t.key!=="Tab"&&(t.stopPropagation(),this.handleDocumentKeyDown(t))}handleClearClick(t){t.stopPropagation(),this.valueHasChanged=!0,this.value!==""&&(this.setSelectedOptions([]),this.displayInput.focus({preventScroll:!0}),this.updateComplete.then(()=>{this.emit("sl-clear"),this.emit("sl-input"),this.emit("sl-change")}))}handleClearMouseDown(t){t.stopPropagation(),t.preventDefault()}handleOptionClick(t){let o=t.target.closest("sl-option"),i=this.value;o&&!o.disabled&&(this.valueHasChanged=!0,this.multiple?this.toggleOptionSelection(o):this.setSelectedOptions(o),this.updateComplete.then(()=>this.displayInput.focus({preventScroll:!0})),this.value!==i&&this.updateComplete.then(()=>{this.emit("sl-input"),this.emit("sl-change")}),this.multiple||(this.hide(),this.displayInput.focus({preventScroll:!0})))}handleDefaultSlotChange(){customElements.get("sl-option")||customElements.whenDefined("sl-option").then(()=>this.handleDefaultSlotChange());let t=this.getAllOptions(),e=this.valueHasChanged?this.value:this.defaultValue,o=Array.isArray(e)?e:[e],i=[];t.forEach(r=>i.push(r.value)),this.setSelectedOptions(t.filter(r=>o.includes(r.value)))}handleTagRemove(t,e){t.stopPropagation(),this.valueHasChanged=!0,this.disabled||(this.toggleOptionSelection(e,!1),this.updateComplete.then(()=>{this.emit("sl-input"),this.emit("sl-change")}))}getAllOptions(){return[...this.querySelectorAll("sl-option")]}getFirstOption(){return this.querySelector("sl-option")}setCurrentOption(t){this.getAllOptions().forEach(o=>{o.current=!1,o.tabIndex=-1}),t&&(this.currentOption=t,t.current=!0,t.tabIndex=0,t.focus())}setSelectedOptions(t){let e=this.getAllOptions(),o=Array.isArray(t)?t:[t];e.forEach(i=>i.selected=!1),o.length&&o.forEach(i=>i.selected=!0),this.selectionChanged()}toggleOptionSelection(t,e){e===!0||e===!1?t.selected=e:t.selected=!t.selected,this.selectionChanged()}selectionChanged(){var t,e,o;let i=this.getAllOptions();this.selectedOptions=i.filter(s=>s.selected);let r=this.valueHasChanged;if(this.multiple)this.value=this.selectedOptions.map(s=>s.value),this.placeholder&&this.value.length===0?this.displayLabel="":this.displayLabel=this.localize.term("numOptionsSelected",this.selectedOptions.length);else{let s=this.selectedOptions[0];this.value=(t=s?.value)!=null?t:"",this.displayLabel=(o=(e=s?.getTextLabel)==null?void 0:e.call(s))!=null?o:""}this.valueHasChanged=r,this.updateComplete.then(()=>{this.formControlController.updateValidity()})}get tags(){return this.selectedOptions.map((t,e)=>{if(e<this.maxOptionsVisible||this.maxOptionsVisible<=0){let o=this.getTag(t,e);return x`<div @sl-remove=${i=>this.handleTagRemove(i,t)}>
          ${typeof o=="string"?Cs(o):o}
        </div>`}else if(e===this.maxOptionsVisible)return x`<sl-tag size=${this.size}>+${this.selectedOptions.length-e}</sl-tag>`;return x``})}handleInvalid(t){this.formControlController.setValidity(!1),this.formControlController.emitInvalidEvent(t)}handleDisabledChange(){this.disabled&&(this.open=!1,this.handleOpenChange())}attributeChangedCallback(t,e,o){if(super.attributeChangedCallback(t,e,o),t==="value"){let i=this.valueHasChanged;this.value=this.defaultValue,this.valueHasChanged=i}}handleValueChange(){if(!this.valueHasChanged){let o=this.valueHasChanged;this.value=this.defaultValue,this.valueHasChanged=o}let t=this.getAllOptions(),e=Array.isArray(this.value)?this.value:[this.value];this.setSelectedOptions(t.filter(o=>e.includes(o.value)))}async handleOpenChange(){if(this.open&&!this.disabled){this.setCurrentOption(this.selectedOptions[0]||this.getFirstOption()),this.emit("sl-show"),this.addOpenListeners(),await Ce(this),this.listbox.hidden=!1,this.popup.active=!0,requestAnimationFrame(()=>{this.setCurrentOption(this.currentOption)});let{keyframes:t,options:e}=_e(this,"select.show",{dir:this.localize.dir()});await xe(this.popup.popup,t,e),this.currentOption&&Br(this.currentOption,this.listbox,"vertical","auto"),this.emit("sl-after-show")}else{this.emit("sl-hide"),this.removeOpenListeners(),await Ce(this);let{keyframes:t,options:e}=_e(this,"select.hide",{dir:this.localize.dir()});await xe(this.popup.popup,t,e),this.listbox.hidden=!0,this.popup.active=!1,this.emit("sl-after-hide")}}async show(){if(this.open||this.disabled){this.open=!1;return}return this.open=!0,we(this,"sl-after-show")}async hide(){if(!this.open||this.disabled){this.open=!1;return}return this.open=!1,we(this,"sl-after-hide")}checkValidity(){return this.valueInput.checkValidity()}getForm(){return this.formControlController.getForm()}reportValidity(){return this.valueInput.reportValidity()}setCustomValidity(t){this.valueInput.setCustomValidity(t),this.formControlController.updateValidity()}focus(t){this.displayInput.focus(t)}blur(){this.displayInput.blur()}render(){let t=this.hasSlotController.test("label"),e=this.hasSlotController.test("help-text"),o=this.label?!0:!!t,i=this.helpText?!0:!!e,r=this.clearable&&!this.disabled&&this.value.length>0,s=this.placeholder&&this.value&&this.value.length<=0;return x`
      <div
        part="form-control"
        class=${R({"form-control":!0,"form-control--small":this.size==="small","form-control--medium":this.size==="medium","form-control--large":this.size==="large","form-control--has-label":o,"form-control--has-help-text":i})}
      >
        <label
          id="label"
          part="form-control-label"
          class="form-control__label"
          aria-hidden=${o?"false":"true"}
          @click=${this.handleLabelClick}
        >
          <slot name="label">${this.label}</slot>
        </label>

        <div part="form-control-input" class="form-control-input">
          <sl-popup
            class=${R({select:!0,"select--standard":!0,"select--filled":this.filled,"select--pill":this.pill,"select--open":this.open,"select--disabled":this.disabled,"select--multiple":this.multiple,"select--focused":this.hasFocus,"select--placeholder-visible":s,"select--top":this.placement==="top","select--bottom":this.placement==="bottom","select--small":this.size==="small","select--medium":this.size==="medium","select--large":this.size==="large"})}
            placement=${this.placement}
            strategy=${this.hoist?"fixed":"absolute"}
            flip
            shift
            sync="width"
            auto-size="vertical"
            auto-size-padding="10"
          >
            <div
              part="combobox"
              class="select__combobox"
              slot="anchor"
              @keydown=${this.handleComboboxKeyDown}
              @mousedown=${this.handleComboboxMouseDown}
            >
              <slot part="prefix" name="prefix" class="select__prefix"></slot>

              <input
                part="display-input"
                class="select__display-input"
                type="text"
                placeholder=${this.placeholder}
                .disabled=${this.disabled}
                .value=${this.displayLabel}
                autocomplete="off"
                spellcheck="false"
                autocapitalize="off"
                readonly
                aria-controls="listbox"
                aria-expanded=${this.open?"true":"false"}
                aria-haspopup="listbox"
                aria-labelledby="label"
                aria-disabled=${this.disabled?"true":"false"}
                aria-describedby="help-text"
                role="combobox"
                tabindex="0"
                @focus=${this.handleFocus}
                @blur=${this.handleBlur}
              />

              ${this.multiple?x`<div part="tags" class="select__tags">${this.tags}</div>`:""}

              <input
                class="select__value-input"
                type="text"
                ?disabled=${this.disabled}
                ?required=${this.required}
                .value=${Array.isArray(this.value)?this.value.join(", "):this.value}
                tabindex="-1"
                aria-hidden="true"
                @focus=${()=>this.focus()}
                @invalid=${this.handleInvalid}
              />

              ${r?x`
                    <button
                      part="clear-button"
                      class="select__clear"
                      type="button"
                      aria-label=${this.localize.term("clearEntry")}
                      @mousedown=${this.handleClearMouseDown}
                      @click=${this.handleClearClick}
                      tabindex="-1"
                    >
                      <slot name="clear-icon">
                        <sl-icon name="x-circle-fill" library="system"></sl-icon>
                      </slot>
                    </button>
                  `:""}

              <slot name="suffix" part="suffix" class="select__suffix"></slot>

              <slot name="expand-icon" part="expand-icon" class="select__expand-icon">
                <sl-icon library="system" name="chevron-down"></sl-icon>
              </slot>
            </div>

            <div
              id="listbox"
              role="listbox"
              aria-expanded=${this.open?"true":"false"}
              aria-multiselectable=${this.multiple?"true":"false"}
              aria-labelledby="label"
              part="listbox"
              class="select__listbox"
              tabindex="-1"
              @mouseup=${this.handleOptionClick}
              @slotchange=${this.handleDefaultSlotChange}
            >
              <slot></slot>
            </div>
          </sl-popup>
        </div>

        <div
          part="form-control-help-text"
          id="help-text"
          class="form-control__help-text"
          aria-hidden=${i?"false":"true"}
        >
          <slot name="help-text">${this.helpText}</slot>
        </div>
      </div>
    `}};C.styles=[I,yt,Mr];C.dependencies={"sl-icon":q,"sl-popup":A,"sl-tag":Ht};n([P(".select")],C.prototype,"popup",2);n([P(".select__combobox")],C.prototype,"combobox",2);n([P(".select__display-input")],C.prototype,"displayInput",2);n([P(".select__value-input")],C.prototype,"valueInput",2);n([P(".select__listbox")],C.prototype,"listbox",2);n([B()],C.prototype,"hasFocus",2);n([B()],C.prototype,"displayLabel",2);n([B()],C.prototype,"currentOption",2);n([B()],C.prototype,"selectedOptions",2);n([B()],C.prototype,"valueHasChanged",2);n([a()],C.prototype,"name",2);n([B()],C.prototype,"value",1);n([a({attribute:"value"})],C.prototype,"defaultValue",2);n([a({reflect:!0})],C.prototype,"size",2);n([a()],C.prototype,"placeholder",2);n([a({type:Boolean,reflect:!0})],C.prototype,"multiple",2);n([a({attribute:"max-options-visible",type:Number})],C.prototype,"maxOptionsVisible",2);n([a({type:Boolean,reflect:!0})],C.prototype,"disabled",2);n([a({type:Boolean})],C.prototype,"clearable",2);n([a({type:Boolean,reflect:!0})],C.prototype,"open",2);n([a({type:Boolean})],C.prototype,"hoist",2);n([a({type:Boolean,reflect:!0})],C.prototype,"filled",2);n([a({type:Boolean,reflect:!0})],C.prototype,"pill",2);n([a()],C.prototype,"label",2);n([a({reflect:!0})],C.prototype,"placement",2);n([a({attribute:"help-text"})],C.prototype,"helpText",2);n([a({reflect:!0})],C.prototype,"form",2);n([a({type:Boolean,reflect:!0})],C.prototype,"required",2);n([a()],C.prototype,"getTag",2);n([S("disabled",{waitUntilFirstUpdate:!0})],C.prototype,"handleDisabledChange",1);n([S(["defaultValue","value"],{waitUntilFirstUpdate:!0})],C.prototype,"handleValueChange",1);n([S("open",{waitUntilFirstUpdate:!0})],C.prototype,"handleOpenChange",1);ye("select.show",{keyframes:[{opacity:0,scale:.9},{opacity:1,scale:1}],options:{duration:100,easing:"ease"}});ye("select.hide",{keyframes:[{opacity:1,scale:1},{opacity:0,scale:.9}],options:{duration:100,easing:"ease"}})});var Ss=f(()=>{pi();C.define("sl-select")});var As=f(()=>{Ss();pi();Jo();Ko();Qo();ti();nt();Xe();mo();at();Zo();Xo();Ye();Ge();Ze();ct();ht();le();xt();he();ae();ce();pe();ne();Y();H();N();M()});var Es,di=f(()=>{T();Es=z`
  :host {
    display: block;
    user-select: none;
    -webkit-user-select: none;
  }

  :host(:focus) {
    outline: none;
  }

  .option {
    position: relative;
    display: flex;
    align-items: center;
    font-family: var(--sl-font-sans);
    font-size: var(--sl-font-size-medium);
    font-weight: var(--sl-font-weight-normal);
    line-height: var(--sl-line-height-normal);
    letter-spacing: var(--sl-letter-spacing-normal);
    color: var(--sl-color-neutral-700);
    padding: var(--sl-spacing-x-small) var(--sl-spacing-medium) var(--sl-spacing-x-small) var(--sl-spacing-x-small);
    transition: var(--sl-transition-fast) fill;
    cursor: pointer;
  }

  .option--hover:not(.option--current):not(.option--disabled) {
    background-color: var(--sl-color-neutral-100);
    color: var(--sl-color-neutral-1000);
  }

  .option--current,
  .option--current.option--disabled {
    background-color: var(--sl-color-primary-600);
    color: var(--sl-color-neutral-0);
    opacity: 1;
  }

  .option--disabled {
    outline: none;
    opacity: 0.5;
    cursor: not-allowed;
  }

  .option__label {
    flex: 1 1 auto;
    display: inline-block;
    line-height: var(--sl-line-height-dense);
  }

  .option .option__check {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    visibility: hidden;
    padding-inline-end: var(--sl-spacing-2x-small);
  }

  .option--selected .option__check {
    visibility: visible;
  }

  .option__prefix,
  .option__suffix {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
  }

  .option__prefix::slotted(*) {
    margin-inline-end: var(--sl-spacing-x-small);
  }

  .option__suffix::slotted(*) {
    margin-inline-start: var(--sl-spacing-x-small);
  }

  @media (forced-colors: active) {
    :host(:hover:not([aria-disabled='true'])) .option {
      outline: dashed 1px SelectedItem;
      outline-offset: -1px;
    }
  }
`});var ot,ui=f(()=>{di();ht();xt();Y();H();N();M();dt();T();et();ot=class extends L{constructor(){super(...arguments),this.localize=new it(this),this.isInitialized=!1,this.current=!1,this.selected=!1,this.hasHover=!1,this.value="",this.disabled=!1}connectedCallback(){super.connectedCallback(),this.setAttribute("role","option"),this.setAttribute("aria-selected","false")}handleDefaultSlotChange(){this.isInitialized?customElements.whenDefined("sl-select").then(()=>{let t=this.closest("sl-select");t&&t.handleDefaultSlotChange()}):this.isInitialized=!0}handleMouseEnter(){this.hasHover=!0}handleMouseLeave(){this.hasHover=!1}handleDisabledChange(){this.setAttribute("aria-disabled",this.disabled?"true":"false")}handleSelectedChange(){this.setAttribute("aria-selected",this.selected?"true":"false")}handleValueChange(){typeof this.value!="string"&&(this.value=String(this.value)),this.value.includes(" ")&&(console.error("Option values cannot include a space. All spaces have been replaced with underscores.",this),this.value=this.value.replace(/ /g,"_"))}getTextLabel(){let t=this.childNodes,e="";return[...t].forEach(o=>{o.nodeType===Node.ELEMENT_NODE&&(o.hasAttribute("slot")||(e+=o.textContent)),o.nodeType===Node.TEXT_NODE&&(e+=o.textContent)}),e.trim()}render(){return x`
      <div
        part="base"
        class=${R({option:!0,"option--current":this.current,"option--disabled":this.disabled,"option--selected":this.selected,"option--hover":this.hasHover})}
        @mouseenter=${this.handleMouseEnter}
        @mouseleave=${this.handleMouseLeave}
      >
        <sl-icon part="checked-icon" class="option__check" name="check" library="system" aria-hidden="true"></sl-icon>
        <slot part="prefix" name="prefix" class="option__prefix"></slot>
        <slot part="label" class="option__label" @slotchange=${this.handleDefaultSlotChange}></slot>
        <slot part="suffix" name="suffix" class="option__suffix"></slot>
      </div>
    `}};ot.styles=[I,Es];ot.dependencies={"sl-icon":q};n([P(".option__label")],ot.prototype,"defaultSlot",2);n([B()],ot.prototype,"current",2);n([B()],ot.prototype,"selected",2);n([B()],ot.prototype,"hasHover",2);n([a({reflect:!0})],ot.prototype,"value",2);n([a({type:Boolean,reflect:!0})],ot.prototype,"disabled",2);n([S("disabled")],ot.prototype,"handleDisabledChange",1);n([S("selected")],ot.prototype,"handleSelectedChange",1);n([S("value")],ot.prototype,"handleValueChange",1)});var zs=f(()=>{ui();ot.define("sl-option")});var Os=f(()=>{zs();ui();di();ht();le();xt();he();ae();ce();pe();ne();Y();H();N();M()});var Ts,fi=f(()=>{T();Ts=z`
  :host {
    display: inline-block;
  }

  :host([size='small']) {
    --height: var(--sl-toggle-size-small);
    --thumb-size: calc(var(--sl-toggle-size-small) + 4px);
    --width: calc(var(--height) * 2);

    font-size: var(--sl-input-font-size-small);
  }

  :host([size='medium']) {
    --height: var(--sl-toggle-size-medium);
    --thumb-size: calc(var(--sl-toggle-size-medium) + 4px);
    --width: calc(var(--height) * 2);

    font-size: var(--sl-input-font-size-medium);
  }

  :host([size='large']) {
    --height: var(--sl-toggle-size-large);
    --thumb-size: calc(var(--sl-toggle-size-large) + 4px);
    --width: calc(var(--height) * 2);

    font-size: var(--sl-input-font-size-large);
  }

  .switch {
    position: relative;
    display: inline-flex;
    align-items: center;
    font-family: var(--sl-input-font-family);
    font-size: inherit;
    font-weight: var(--sl-input-font-weight);
    color: var(--sl-input-label-color);
    vertical-align: middle;
    cursor: pointer;
  }

  .switch__control {
    flex: 0 0 auto;
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--width);
    height: var(--height);
    background-color: var(--sl-color-neutral-400);
    border: solid var(--sl-input-border-width) var(--sl-color-neutral-400);
    border-radius: var(--height);
    transition:
      var(--sl-transition-fast) border-color,
      var(--sl-transition-fast) background-color;
  }

  .switch__control .switch__thumb {
    width: var(--thumb-size);
    height: var(--thumb-size);
    background-color: var(--sl-color-neutral-0);
    border-radius: 50%;
    border: solid var(--sl-input-border-width) var(--sl-color-neutral-400);
    translate: calc((var(--width) - var(--height)) / -2);
    transition:
      var(--sl-transition-fast) translate ease,
      var(--sl-transition-fast) background-color,
      var(--sl-transition-fast) border-color,
      var(--sl-transition-fast) box-shadow;
  }

  .switch__input {
    position: absolute;
    opacity: 0;
    padding: 0;
    margin: 0;
    pointer-events: none;
  }

  /* Hover */
  .switch:not(.switch--checked):not(.switch--disabled) .switch__control:hover {
    background-color: var(--sl-color-neutral-400);
    border-color: var(--sl-color-neutral-400);
  }

  .switch:not(.switch--checked):not(.switch--disabled) .switch__control:hover .switch__thumb {
    background-color: var(--sl-color-neutral-0);
    border-color: var(--sl-color-neutral-400);
  }

  /* Focus */
  .switch:not(.switch--checked):not(.switch--disabled) .switch__input:focus-visible ~ .switch__control {
    background-color: var(--sl-color-neutral-400);
    border-color: var(--sl-color-neutral-400);
  }

  .switch:not(.switch--checked):not(.switch--disabled) .switch__input:focus-visible ~ .switch__control .switch__thumb {
    background-color: var(--sl-color-neutral-0);
    border-color: var(--sl-color-primary-600);
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  /* Checked */
  .switch--checked .switch__control {
    background-color: var(--sl-color-primary-600);
    border-color: var(--sl-color-primary-600);
  }

  .switch--checked .switch__control .switch__thumb {
    background-color: var(--sl-color-neutral-0);
    border-color: var(--sl-color-primary-600);
    translate: calc((var(--width) - var(--height)) / 2);
  }

  /* Checked + hover */
  .switch.switch--checked:not(.switch--disabled) .switch__control:hover {
    background-color: var(--sl-color-primary-600);
    border-color: var(--sl-color-primary-600);
  }

  .switch.switch--checked:not(.switch--disabled) .switch__control:hover .switch__thumb {
    background-color: var(--sl-color-neutral-0);
    border-color: var(--sl-color-primary-600);
  }

  /* Checked + focus */
  .switch.switch--checked:not(.switch--disabled) .switch__input:focus-visible ~ .switch__control {
    background-color: var(--sl-color-primary-600);
    border-color: var(--sl-color-primary-600);
  }

  .switch.switch--checked:not(.switch--disabled) .switch__input:focus-visible ~ .switch__control .switch__thumb {
    background-color: var(--sl-color-neutral-0);
    border-color: var(--sl-color-primary-600);
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  /* Disabled */
  .switch--disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .switch__label {
    display: inline-block;
    line-height: var(--height);
    margin-inline-start: 0.5em;
    user-select: none;
    -webkit-user-select: none;
  }

  :host([required]) .switch__label::after {
    content: var(--sl-input-required-content);
    color: var(--sl-input-required-content-color);
    margin-inline-start: var(--sl-input-required-content-offset);
  }

  @media (forced-colors: active) {
    .switch.switch--checked:not(.switch--disabled) .switch__control:hover .switch__thumb,
    .switch--checked .switch__control .switch__thumb {
      background-color: ButtonText;
    }
  }
`});var W,mi=f(()=>{fi();Ot();nt();at();ct();Y();H();N();M();dt();T();fe();Fe();et();W=class extends L{constructor(){super(...arguments),this.formControlController=new _t(this,{value:t=>t.checked?t.value||"on":void 0,defaultValue:t=>t.defaultChecked,setValue:(t,e)=>t.checked=e}),this.hasSlotController=new wt(this,"help-text"),this.hasFocus=!1,this.title="",this.name="",this.size="medium",this.disabled=!1,this.checked=!1,this.defaultChecked=!1,this.form="",this.required=!1,this.helpText=""}get validity(){return this.input.validity}get validationMessage(){return this.input.validationMessage}firstUpdated(){this.formControlController.updateValidity()}handleBlur(){this.hasFocus=!1,this.emit("sl-blur")}handleInput(){this.emit("sl-input")}handleInvalid(t){this.formControlController.setValidity(!1),this.formControlController.emitInvalidEvent(t)}handleClick(){this.checked=!this.checked,this.emit("sl-change")}handleFocus(){this.hasFocus=!0,this.emit("sl-focus")}handleKeyDown(t){t.key==="ArrowLeft"&&(t.preventDefault(),this.checked=!1,this.emit("sl-change"),this.emit("sl-input")),t.key==="ArrowRight"&&(t.preventDefault(),this.checked=!0,this.emit("sl-change"),this.emit("sl-input"))}handleCheckedChange(){this.input.checked=this.checked,this.formControlController.updateValidity()}handleDisabledChange(){this.formControlController.setValidity(!0)}click(){this.input.click()}focus(t){this.input.focus(t)}blur(){this.input.blur()}checkValidity(){return this.input.checkValidity()}getForm(){return this.formControlController.getForm()}reportValidity(){return this.input.reportValidity()}setCustomValidity(t){this.input.setCustomValidity(t),this.formControlController.updateValidity()}render(){let t=this.hasSlotController.test("help-text"),e=this.helpText?!0:!!t;return x`
      <div
        class=${R({"form-control":!0,"form-control--small":this.size==="small","form-control--medium":this.size==="medium","form-control--large":this.size==="large","form-control--has-help-text":e})}
      >
        <label
          part="base"
          class=${R({switch:!0,"switch--checked":this.checked,"switch--disabled":this.disabled,"switch--focused":this.hasFocus,"switch--small":this.size==="small","switch--medium":this.size==="medium","switch--large":this.size==="large"})}
        >
          <input
            class="switch__input"
            type="checkbox"
            title=${this.title}
            name=${this.name}
            value=${y(this.value)}
            .checked=${Pt(this.checked)}
            .disabled=${this.disabled}
            .required=${this.required}
            role="switch"
            aria-checked=${this.checked?"true":"false"}
            aria-describedby="help-text"
            @click=${this.handleClick}
            @input=${this.handleInput}
            @invalid=${this.handleInvalid}
            @blur=${this.handleBlur}
            @focus=${this.handleFocus}
            @keydown=${this.handleKeyDown}
          />

          <span part="control" class="switch__control">
            <span part="thumb" class="switch__thumb"></span>
          </span>

          <div part="label" class="switch__label">
            <slot></slot>
          </div>
        </label>

        <div
          aria-hidden=${e?"false":"true"}
          class="form-control__help-text"
          id="help-text"
          part="form-control-help-text"
        >
          <slot name="help-text">${this.helpText}</slot>
        </div>
      </div>
    `}};W.styles=[I,yt,Ts];n([P('input[type="checkbox"]')],W.prototype,"input",2);n([B()],W.prototype,"hasFocus",2);n([a()],W.prototype,"title",2);n([a()],W.prototype,"name",2);n([a()],W.prototype,"value",2);n([a({reflect:!0})],W.prototype,"size",2);n([a({type:Boolean,reflect:!0})],W.prototype,"disabled",2);n([a({type:Boolean,reflect:!0})],W.prototype,"checked",2);n([Bt("checked")],W.prototype,"defaultChecked",2);n([a({reflect:!0})],W.prototype,"form",2);n([a({type:Boolean,reflect:!0})],W.prototype,"required",2);n([a({attribute:"help-text"})],W.prototype,"helpText",2);n([S("checked",{waitUntilFirstUpdate:!0})],W.prototype,"handleCheckedChange",1);n([S("disabled",{waitUntilFirstUpdate:!0})],W.prototype,"handleDisabledChange",1)});var Ps=f(()=>{mi();W.define("sl-switch")});var Ls=f(()=>{Ps();mi();fi();Ot();nt();at();ct();Y();H();N();M()});var Rs,gi=f(()=>{T();Rs=z`
  :host {
    display: inline-block;
  }

  .checkbox {
    position: relative;
    display: inline-flex;
    align-items: flex-start;
    font-family: var(--sl-input-font-family);
    font-weight: var(--sl-input-font-weight);
    color: var(--sl-input-label-color);
    vertical-align: middle;
    cursor: pointer;
  }

  .checkbox--small {
    --toggle-size: var(--sl-toggle-size-small);
    font-size: var(--sl-input-font-size-small);
  }

  .checkbox--medium {
    --toggle-size: var(--sl-toggle-size-medium);
    font-size: var(--sl-input-font-size-medium);
  }

  .checkbox--large {
    --toggle-size: var(--sl-toggle-size-large);
    font-size: var(--sl-input-font-size-large);
  }

  .checkbox__control {
    flex: 0 0 auto;
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--toggle-size);
    height: var(--toggle-size);
    border: solid var(--sl-input-border-width) var(--sl-input-border-color);
    border-radius: 2px;
    background-color: var(--sl-input-background-color);
    color: var(--sl-color-neutral-0);
    transition:
      var(--sl-transition-fast) border-color,
      var(--sl-transition-fast) background-color,
      var(--sl-transition-fast) color,
      var(--sl-transition-fast) box-shadow;
  }

  .checkbox__input {
    position: absolute;
    opacity: 0;
    padding: 0;
    margin: 0;
    pointer-events: none;
  }

  .checkbox__checked-icon,
  .checkbox__indeterminate-icon {
    display: inline-flex;
    width: var(--toggle-size);
    height: var(--toggle-size);
  }

  /* Hover */
  .checkbox:not(.checkbox--checked):not(.checkbox--disabled) .checkbox__control:hover {
    border-color: var(--sl-input-border-color-hover);
    background-color: var(--sl-input-background-color-hover);
  }

  /* Focus */
  .checkbox:not(.checkbox--checked):not(.checkbox--disabled) .checkbox__input:focus-visible ~ .checkbox__control {
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  /* Checked/indeterminate */
  .checkbox--checked .checkbox__control,
  .checkbox--indeterminate .checkbox__control {
    border-color: var(--sl-color-primary-600);
    background-color: var(--sl-color-primary-600);
  }

  /* Checked/indeterminate + hover */
  .checkbox.checkbox--checked:not(.checkbox--disabled) .checkbox__control:hover,
  .checkbox.checkbox--indeterminate:not(.checkbox--disabled) .checkbox__control:hover {
    border-color: var(--sl-color-primary-500);
    background-color: var(--sl-color-primary-500);
  }

  /* Checked/indeterminate + focus */
  .checkbox.checkbox--checked:not(.checkbox--disabled) .checkbox__input:focus-visible ~ .checkbox__control,
  .checkbox.checkbox--indeterminate:not(.checkbox--disabled) .checkbox__input:focus-visible ~ .checkbox__control {
    outline: var(--sl-focus-ring);
    outline-offset: var(--sl-focus-ring-offset);
  }

  /* Disabled */
  .checkbox--disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .checkbox__label {
    display: inline-block;
    color: var(--sl-input-label-color);
    line-height: var(--toggle-size);
    margin-inline-start: 0.5em;
    user-select: none;
    -webkit-user-select: none;
  }

  :host([required]) .checkbox__label::after {
    content: var(--sl-input-required-content);
    color: var(--sl-input-required-content-color);
    margin-inline-start: var(--sl-input-required-content-offset);
  }
`});var U,vi=f(()=>{gi();Ot();nt();at();ct();xt();Y();H();N();M();dt();T();fe();Fe();et();U=class extends L{constructor(){super(...arguments),this.formControlController=new _t(this,{value:t=>t.checked?t.value||"on":void 0,defaultValue:t=>t.defaultChecked,setValue:(t,e)=>t.checked=e}),this.hasSlotController=new wt(this,"help-text"),this.hasFocus=!1,this.title="",this.name="",this.size="medium",this.disabled=!1,this.checked=!1,this.indeterminate=!1,this.defaultChecked=!1,this.form="",this.required=!1,this.helpText=""}get validity(){return this.input.validity}get validationMessage(){return this.input.validationMessage}firstUpdated(){this.formControlController.updateValidity()}handleClick(){this.checked=!this.checked,this.indeterminate=!1,this.emit("sl-change")}handleBlur(){this.hasFocus=!1,this.emit("sl-blur")}handleInput(){this.emit("sl-input")}handleInvalid(t){this.formControlController.setValidity(!1),this.formControlController.emitInvalidEvent(t)}handleFocus(){this.hasFocus=!0,this.emit("sl-focus")}handleDisabledChange(){this.formControlController.setValidity(this.disabled)}handleStateChange(){this.input.checked=this.checked,this.input.indeterminate=this.indeterminate,this.formControlController.updateValidity()}click(){this.input.click()}focus(t){this.input.focus(t)}blur(){this.input.blur()}checkValidity(){return this.input.checkValidity()}getForm(){return this.formControlController.getForm()}reportValidity(){return this.input.reportValidity()}setCustomValidity(t){this.input.setCustomValidity(t),this.formControlController.updateValidity()}render(){let t=this.hasSlotController.test("help-text"),e=this.helpText?!0:!!t;return x`
      <div
        class=${R({"form-control":!0,"form-control--small":this.size==="small","form-control--medium":this.size==="medium","form-control--large":this.size==="large","form-control--has-help-text":e})}
      >
        <label
          part="base"
          class=${R({checkbox:!0,"checkbox--checked":this.checked,"checkbox--disabled":this.disabled,"checkbox--focused":this.hasFocus,"checkbox--indeterminate":this.indeterminate,"checkbox--small":this.size==="small","checkbox--medium":this.size==="medium","checkbox--large":this.size==="large"})}
        >
          <input
            class="checkbox__input"
            type="checkbox"
            title=${this.title}
            name=${this.name}
            value=${y(this.value)}
            .indeterminate=${Pt(this.indeterminate)}
            .checked=${Pt(this.checked)}
            .disabled=${this.disabled}
            .required=${this.required}
            aria-checked=${this.checked?"true":"false"}
            aria-describedby="help-text"
            @click=${this.handleClick}
            @input=${this.handleInput}
            @invalid=${this.handleInvalid}
            @blur=${this.handleBlur}
            @focus=${this.handleFocus}
          />

          <span
            part="control${this.checked?" control--checked":""}${this.indeterminate?" control--indeterminate":""}"
            class="checkbox__control"
          >
            ${this.checked?x`
                  <sl-icon part="checked-icon" class="checkbox__checked-icon" library="system" name="check"></sl-icon>
                `:""}
            ${!this.checked&&this.indeterminate?x`
                  <sl-icon
                    part="indeterminate-icon"
                    class="checkbox__indeterminate-icon"
                    library="system"
                    name="indeterminate"
                  ></sl-icon>
                `:""}
          </span>

          <div part="label" class="checkbox__label">
            <slot></slot>
          </div>
        </label>

        <div
          aria-hidden=${e?"false":"true"}
          class="form-control__help-text"
          id="help-text"
          part="form-control-help-text"
        >
          <slot name="help-text">${this.helpText}</slot>
        </div>
      </div>
    `}};U.styles=[I,yt,Rs];U.dependencies={"sl-icon":q};n([P('input[type="checkbox"]')],U.prototype,"input",2);n([B()],U.prototype,"hasFocus",2);n([a()],U.prototype,"title",2);n([a()],U.prototype,"name",2);n([a()],U.prototype,"value",2);n([a({reflect:!0})],U.prototype,"size",2);n([a({type:Boolean,reflect:!0})],U.prototype,"disabled",2);n([a({type:Boolean,reflect:!0})],U.prototype,"checked",2);n([a({type:Boolean,reflect:!0})],U.prototype,"indeterminate",2);n([Bt("checked")],U.prototype,"defaultChecked",2);n([a({reflect:!0})],U.prototype,"form",2);n([a({type:Boolean,reflect:!0})],U.prototype,"required",2);n([a({attribute:"help-text"})],U.prototype,"helpText",2);n([S("disabled",{waitUntilFirstUpdate:!0})],U.prototype,"handleDisabledChange",1);n([S(["checked","indeterminate"],{waitUntilFirstUpdate:!0})],U.prototype,"handleStateChange",1)});var Vs=f(()=>{vi();U.define("sl-checkbox")});var Ds=f(()=>{Vs();vi();gi();Ot();nt();at();ct();xt();he();ae();ce();pe();ne();Y();H();N();M()});var Ms,bi=f(()=>{T();Ms=z`
  :host {
    --max-width: 20rem;
    --hide-delay: 0ms;
    --show-delay: 150ms;

    display: contents;
  }

  .tooltip {
    --arrow-size: var(--sl-tooltip-arrow-size);
    --arrow-color: var(--sl-tooltip-background-color);
  }

  .tooltip::part(popup) {
    z-index: var(--sl-z-index-tooltip);
  }

  .tooltip[placement^='top']::part(popup) {
    transform-origin: bottom;
  }

  .tooltip[placement^='bottom']::part(popup) {
    transform-origin: top;
  }

  .tooltip[placement^='left']::part(popup) {
    transform-origin: right;
  }

  .tooltip[placement^='right']::part(popup) {
    transform-origin: left;
  }

  .tooltip__body {
    display: block;
    width: max-content;
    max-width: var(--max-width);
    border-radius: var(--sl-tooltip-border-radius);
    background-color: var(--sl-tooltip-background-color);
    font-family: var(--sl-tooltip-font-family);
    font-size: var(--sl-tooltip-font-size);
    font-weight: var(--sl-tooltip-font-weight);
    line-height: var(--sl-tooltip-line-height);
    text-align: start;
    white-space: normal;
    color: var(--sl-tooltip-color);
    padding: var(--sl-tooltip-padding);
    pointer-events: none;
    user-select: none;
    -webkit-user-select: none;
  }
`});var j,yi=f(()=>{bi();Xe();Ye();Ge();Ze();ht();Y();H();N();M();dt();T();et();j=class extends L{constructor(){super(),this.localize=new it(this),this.content="",this.placement="top",this.disabled=!1,this.distance=8,this.open=!1,this.skidding=0,this.trigger="hover focus",this.hoist=!1,this.handleBlur=()=>{this.hasTrigger("focus")&&this.hide()},this.handleClick=()=>{this.hasTrigger("click")&&(this.open?this.hide():this.show())},this.handleFocus=()=>{this.hasTrigger("focus")&&this.show()},this.handleDocumentKeyDown=t=>{t.key==="Escape"&&(t.stopPropagation(),this.hide())},this.handleMouseOver=()=>{if(this.hasTrigger("hover")){let t=hi(getComputedStyle(this).getPropertyValue("--show-delay"));clearTimeout(this.hoverTimeout),this.hoverTimeout=window.setTimeout(()=>this.show(),t)}},this.handleMouseOut=()=>{if(this.hasTrigger("hover")){let t=hi(getComputedStyle(this).getPropertyValue("--hide-delay"));clearTimeout(this.hoverTimeout),this.hoverTimeout=window.setTimeout(()=>this.hide(),t)}},this.addEventListener("blur",this.handleBlur,!0),this.addEventListener("focus",this.handleFocus,!0),this.addEventListener("click",this.handleClick),this.addEventListener("mouseover",this.handleMouseOver),this.addEventListener("mouseout",this.handleMouseOut)}disconnectedCallback(){var t;super.disconnectedCallback(),(t=this.closeWatcher)==null||t.destroy(),document.removeEventListener("keydown",this.handleDocumentKeyDown)}firstUpdated(){this.body.hidden=!this.open,this.open&&(this.popup.active=!0,this.popup.reposition())}hasTrigger(t){return this.trigger.split(" ").includes(t)}async handleOpenChange(){var t,e;if(this.open){if(this.disabled)return;this.emit("sl-show"),"CloseWatcher"in window?((t=this.closeWatcher)==null||t.destroy(),this.closeWatcher=new CloseWatcher,this.closeWatcher.onclose=()=>{this.hide()}):document.addEventListener("keydown",this.handleDocumentKeyDown),await Ce(this.body),this.body.hidden=!1,this.popup.active=!0;let{keyframes:o,options:i}=_e(this,"tooltip.show",{dir:this.localize.dir()});await xe(this.popup.popup,o,i),this.popup.reposition(),this.emit("sl-after-show")}else{this.emit("sl-hide"),(e=this.closeWatcher)==null||e.destroy(),document.removeEventListener("keydown",this.handleDocumentKeyDown),await Ce(this.body);let{keyframes:o,options:i}=_e(this,"tooltip.hide",{dir:this.localize.dir()});await xe(this.popup.popup,o,i),this.popup.active=!1,this.body.hidden=!0,this.emit("sl-after-hide")}}async handleOptionsChange(){this.hasUpdated&&(await this.updateComplete,this.popup.reposition())}handleDisabledChange(){this.disabled&&this.open&&this.hide()}async show(){if(!this.open)return this.open=!0,we(this,"sl-after-show")}async hide(){if(this.open)return this.open=!1,we(this,"sl-after-hide")}render(){return x`
      <sl-popup
        part="base"
        exportparts="
          popup:base__popup,
          arrow:base__arrow
        "
        class=${R({tooltip:!0,"tooltip--open":this.open})}
        placement=${this.placement}
        distance=${this.distance}
        skidding=${this.skidding}
        strategy=${this.hoist?"fixed":"absolute"}
        flip
        shift
        arrow
        hover-bridge
      >
        ${""}
        <slot slot="anchor" aria-describedby="tooltip"></slot>

        ${""}
        <div part="body" id="tooltip" class="tooltip__body" role="tooltip" aria-live=${this.open?"polite":"off"}>
          <slot name="content">${this.content}</slot>
        </div>
      </sl-popup>
    `}};j.styles=[I,Ms];j.dependencies={"sl-popup":A};n([P("slot:not([name])")],j.prototype,"defaultSlot",2);n([P(".tooltip__body")],j.prototype,"body",2);n([P("sl-popup")],j.prototype,"popup",2);n([a()],j.prototype,"content",2);n([a()],j.prototype,"placement",2);n([a({type:Boolean,reflect:!0})],j.prototype,"disabled",2);n([a({type:Number})],j.prototype,"distance",2);n([a({type:Boolean,reflect:!0})],j.prototype,"open",2);n([a({type:Number})],j.prototype,"skidding",2);n([a()],j.prototype,"trigger",2);n([a({type:Boolean})],j.prototype,"hoist",2);n([S("open",{waitUntilFirstUpdate:!0})],j.prototype,"handleOpenChange",1);n([S(["content","distance","hoist","placement","skidding"])],j.prototype,"handleOptionsChange",1);n([S("disabled")],j.prototype,"handleDisabledChange",1);ye("tooltip.show",{keyframes:[{opacity:0,scale:.8},{opacity:1,scale:1}],options:{duration:150,easing:"ease"}});ye("tooltip.hide",{keyframes:[{opacity:1,scale:1},{opacity:0,scale:.8}],options:{duration:150,easing:"ease"}})});var Bs=f(()=>{yi();j.define("sl-tooltip")});var Is=f(()=>{Bs();yi();bi();Xe();mo();Ye();Ge();Ze();ht();le();Y();H();N();M()});var Nl=Hs(()=>{Sr();zr();As();Os();Ls();Ds();Is()});export default Nl();
/*! Bundled license information:

@lit/reactive-element/css-tag.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/reactive-element/reactive-element.js:
lit-html/lit-html.js:
lit-element/lit-element.js:
@lit/reactive-element/decorators/custom-element.js:
@lit/reactive-element/decorators/property.js:
@lit/reactive-element/decorators/state.js:
@lit/reactive-element/decorators/event-options.js:
@lit/reactive-element/decorators/base.js:
@lit/reactive-element/decorators/query.js:
@lit/reactive-element/decorators/query-all.js:
@lit/reactive-element/decorators/query-async.js:
@lit/reactive-element/decorators/query-assigned-nodes.js:
lit-html/directive.js:
lit-html/directives/unsafe-html.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/is-server.js:
  (**
   * @license
   * Copyright 2022 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/reactive-element/decorators/query-assigned-elements.js:
  (**
   * @license
   * Copyright 2021 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/directive-helpers.js:
lit-html/directives/live.js:
lit-html/static.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/directives/class-map.js:
lit-html/directives/if-defined.js:
  (**
   * @license
   * Copyright 2018 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)
*/
