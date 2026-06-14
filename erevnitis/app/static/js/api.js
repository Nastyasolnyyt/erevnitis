/**
 * Erevnitis SRE Panel — API Client & Utilities
 * api.js
 */

// ── Token helpers ────────────────────────────────────────────────────────────
const Auth = {
  getToken:    () => localStorage.getItem('ev_token'),
  getRole:     () => localStorage.getItem('ev_role'),
  getUsername: () => localStorage.getItem('ev_user'),
  isLoggedIn:  () => !!localStorage.getItem('ev_token'),

  save(token, role, username) {
    localStorage.setItem('ev_token',   token);
    localStorage.setItem('ev_role',    role);
    localStorage.setItem('ev_user',    username);
  },

  logout() {
    localStorage.clear();
    window.location.href = '/login';
  },

  requireAuth() {
    if (!this.isLoggedIn()) window.location.href = '/login';
  },

  can(action) {
    const role = this.getRole();
    const perms = {
      admin:  ['read', 'write', 'delete', 'manage_users'],
      sre:    ['read', 'write'],
      analyst:['read', 'export'],
      viewer: ['read'],
    };
    return (perms[role] || []).includes(action);
  },
};

// ── HTTP Client ───────────────────────────────────────────────────────────────
const api = {
  baseURL: '',

  _headers(extra = {}) {
    const h = { 'Content-Type': 'application/json', ...extra };
    const token = Auth.getToken();
    if (token) h['Authorization'] = `Bearer ${token}`;
    return h;
  },

  async _request(method, path, body = null) {
    const opts = { method, headers: this._headers() };
    if (body !== null) opts.body = JSON.stringify(body);

    const res = await fetch(this.baseURL + path, opts);

    if (res.status === 401) {
      Auth.logout();
      return null;
    }

    if (res.status === 204) return null;

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const msg = data.detail || `HTTP ${res.status}`;
      throw new Error(Array.isArray(msg) ? msg.map(e => e.msg).join(', ') : msg);
    }

    return data;
  },

  get:    (path)         => api._request('GET',    path),
  post:   (path, body)   => api._request('POST',   path, body),
  patch:  (path, body)   => api._request('PATCH',  path, body),
  delete: (path)         => api._request('DELETE', path),

  async login(username, password) {
    const body = new URLSearchParams({ username, password });
    const res  = await fetch('/api/v1/auth/token', {
      method:  'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка входа');
    return data;
  },

  // Nodes
  nodes: {
    list:    (params = '') => api.get(`/api/v1/nodes/${params}`),
    get:     (id)          => api.get(`/api/v1/nodes/${id}`),
    create:  (data)        => api.post('/api/v1/nodes/', data),
    update:  (id, data)    => api.patch(`/api/v1/nodes/${id}`, data),
    remove:  (id)          => api.delete(`/api/v1/nodes/${id}`),
    stats:   ()            => api.get('/api/v1/nodes/stats/summary'),
    agentScript: (id)      => `/api/v1/metrics/node/${id}/agent-script`,
  },

  // Incidents
  incidents: {
    list:    (params = '') => api.get(`/api/v1/incidents/${params}`),
    get:     (id)          => api.get(`/api/v1/incidents/${id}`),
    create:  (data)        => api.post('/api/v1/incidents/', data),
    update:  (id, data)    => api.patch(`/api/v1/incidents/${id}`, data),
    remove:  (id)          => api.delete(`/api/v1/incidents/${id}`),
    stats:   ()            => api.get('/api/v1/incidents/stats/summary'),
    exportCSV: ()          => `/api/v1/incidents/export/csv`,
  },

  // Metrics
  metrics: {
    summary:   (nodeId)              => api.get(`/api/v1/metrics/node/${nodeId}/summary`),
    series:    (nodeId, metric, hours) => api.get(`/api/v1/metrics/node/${nodeId}/all-series?hours=${hours || 24}`),
    exportCSV: (nodeId)              => `/api/v1/metrics/node/${nodeId}/export/csv`,
  },

  // Audit
  audit: {
    list: (params = '') => api.get(`/api/v1/audit/${params}`),
  },

  // Auth
  auth: {
    me:      ()     => api.get('/api/v1/auth/me'),
    users:   ()     => api.get('/api/v1/auth/users'),
    register:(data) => api.post('/api/v1/auth/register', data),
  },
};

// ── Toast Notifications ───────────────────────────────────────────────────────
const Toast = {
  container: null,

  init() {
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toast-container';
      document.body.appendChild(this.container);
    }
  },

  show(message, type = 'info', duration = 3500) {
    this.init();
    const icons = { success: 'bi-check-circle-fill', error: 'bi-x-circle-fill',
                    warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<i class="bi ${icons[type] || icons.info}"></i><span>${message}</span>`;
    this.container.appendChild(el);

    setTimeout(() => {
      el.style.animation = 'slideOut 0.2s ease forwards';
      setTimeout(() => el.remove(), 200);
    }, duration);
  },

  success: (msg) => Toast.show(msg, 'success'),
  error:   (msg) => Toast.show(msg, 'error'),
  warning: (msg) => Toast.show(msg, 'warning'),
  info:    (msg) => Toast.show(msg, 'info'),
};

// ── Modal helper ──────────────────────────────────────────────────────────────
const Modal = {
  open(id) {
    const el = document.getElementById(id);
    if (el) { el.classList.add('open'); document.body.style.overflow = 'hidden'; }
  },
  close(id) {
    const el = document.getElementById(id);
    if (el) { el.classList.remove('open'); document.body.style.overflow = ''; }
  },
  closeAll() {
    document.querySelectorAll('.modal-overlay.open').forEach(el => {
      el.classList.remove('open');
    });
    document.body.style.overflow = '';
  },
};

// Close modal on overlay click
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) Modal.closeAll();
});

// Close modal on Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') Modal.closeAll();
});

// ── Format helpers ────────────────────────────────────────────────────────────
const fmt = {
  date(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
      + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  },

  reltime(iso) {
    if (!iso) return '—';
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return 'только что';
    if (m < 60) return `${m} мин. назад`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} ч. назад`;
    return `${Math.floor(h / 24)} д. назад`;
  },

  mttr(createdIso, resolvedIso) {
    if (!createdIso || !resolvedIso) return '—';
    const ms = new Date(resolvedIso) - new Date(createdIso);
    const m  = Math.floor(ms / 60000);
    if (m < 60) return `${m} мин.`;
    const h = Math.floor(m / 60);
    return h < 24 ? `${h} ч. ${m % 60} мин.` : `${Math.floor(h/24)} д. ${h%24} ч.`;
  },

  percent(val) {
    if (val === null || val === undefined) return '—';
    return `${parseFloat(val).toFixed(1)}%`;
  },

  bytes(mb) {
    if (mb === null || mb === undefined) return '—';
    return `${parseFloat(mb).toFixed(2)} MB/s`;
  },

  severity(s) {
    const map = { critical: 'Критичный', high: 'Высокий', medium: 'Средний', low: 'Низкий' };
    return map[s] || s;
  },

  status(s) {
    const map = { open: 'Открыт', investigating: 'Расследование', resolved: 'Решён' };
    return map[s] || s;
  },

  severityBadge(s) {
    return `<span class="badge badge-${s}"><span class="badge-dot"></span>${fmt.severity(s)}</span>`;
  },

  statusBadge(s) {
    return `<span class="badge badge-${s}">${fmt.status(s)}</span>`;
  },

  onlineBadge(online) {
    return online
      ? `<span class="badge badge-online"><span class="badge-dot"></span>Online</span>`
      : `<span class="badge badge-offline"><span class="badge-dot"></span>Offline</span>`;
  },
};

// ── Navbar user info ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const username = Auth.getUsername();
  const role     = Auth.getRole();

  const userPill = document.getElementById('user-pill');
  if (userPill && username) {
    const initials = username.slice(0, 2).toUpperCase();
    userPill.innerHTML = `
      <div class="user-avatar">${initials}</div>
      <span>${username}</span>
      <span class="text-muted" style="font-size:.75rem">${role}</span>
    `;
  }

  // Скрываем кнопки по ролям
  // viewer — только чтение, нет кнопок создания/редактирования
  if (role === 'viewer') {
    document.querySelectorAll('.role-write').forEach(el => el.style.display = 'none');
  }
  // analyst — только чтение + экспорт, нет кнопок создания/редактирования
  if (role === 'analyst') {
    document.querySelectorAll('.role-write').forEach(el => el.style.display = 'none');
  }
  // не admin — нет кнопок удаления и управления пользователями
  if (role !== 'admin') {
    document.querySelectorAll('.role-admin').forEach(el => el.style.display = 'none');
  }

  // Active sidebar link
  const path = window.location.pathname;
  document.querySelectorAll('.sidebar-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href && (path === href || (href !== '/' && path.startsWith(href)))) {
      link.classList.add('active');
    }
  });
});