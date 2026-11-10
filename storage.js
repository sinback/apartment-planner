// Browser storage for the app: IndexedDB through the vendored `idb` library (vendor/idb, global `idb`).
//
// One database, two object stores:
//   floorplans  one record per floorplan, keyed by `id`. The built-in plan is seeded as id "default".
//   layouts     the furniture for one floorplan, keyed by `planId`: { planId, pieces, updatedAt }.
//
// The localStorage-era app kept its single layout under LEGACY_KEY. The first run copies it into
// `layouts` and leaves the old key alone as a backup. If IndexedDB can't be opened (some private
// browsing modes block it), everything falls back to that localStorage key, as before.
window.AptStorage = (() => {
  const DB_NAME = 'apartment-planner', DB_VERSION = 1;
  const LEGACY_KEY = 'apt-furniture-layout-v1';
  const DEFAULT_PLAN = {
    id: 'default', name: 'My apartment', builtin: true,
    image: { src: 'plans/default.png', w: 1194, h: 703 }, pxPerFt: 16,
  };

  let db = null;

  const readLegacy = () => {
    try {
      const s = JSON.parse(localStorage.getItem(LEGACY_KEY));
      return Array.isArray(s) ? s.map(({ id, ...rest }) => rest) : null;
    } catch (e) { return null; }
  };

  async function init() {
    try {
      db = await idb.openDB(DB_NAME, DB_VERSION, {
        upgrade(d, oldVersion) {
          if (oldVersion < 1) {
            d.createObjectStore('floorplans', { keyPath: 'id' });
            d.createObjectStore('layouts', { keyPath: 'planId' });
          }
        },
        // another tab is opening a newer version of the database: let it
        blocking() { db && db.close(); db = null; },
      });
      await migrate();
    } catch (e) {
      console.warn('IndexedDB unavailable; using localStorage instead.', e);
      db = null;
    }
    return { usingIndexedDB: !!db };
  }

  // Seed the built-in floorplan, and copy over a layout saved by the localStorage-era app.
  async function migrate() {
    const tx = db.transaction(['floorplans', 'layouts'], 'readwrite');
    const plans = tx.objectStore('floorplans'), layouts = tx.objectStore('layouts');
    if (!(await plans.get(DEFAULT_PLAN.id))) await plans.put({ ...DEFAULT_PLAN, createdAt: Date.now() });
    if (!(await layouts.get(DEFAULT_PLAN.id))) {
      const legacy = readLegacy();
      if (legacy) await layouts.put({ planId: DEFAULT_PLAN.id, pieces: legacy, updatedAt: Date.now() });
    }
    await tx.done;
  }

  // ---- layouts ----
  async function loadLayout(planId) {
    if (!db) return planId === DEFAULT_PLAN.id ? readLegacy() : null;
    const rec = await db.get('layouts', planId);
    return rec ? rec.pieces : null;
  }

  // Called on every render, so writes are coalesced: while one is in flight, only the newest
  // pending layout per plan is kept, and it is written next.
  const pending = new Map();
  let writing = false;
  function saveLayout(planId, pieces) {
    const clean = pieces.map(({ id, ...rest }) => rest);
    if (!db) {
      if (planId === DEFAULT_PLAN.id) try { localStorage.setItem(LEGACY_KEY, JSON.stringify(clean)); } catch (e) {}
      return;
    }
    pending.set(planId, { planId, pieces: clean, updatedAt: Date.now() });
    if (!writing) flush();
  }
  async function flush() {
    writing = true;
    while (pending.size && db) {
      const [planId, rec] = pending.entries().next().value;
      pending.delete(planId);
      try { await db.put('layouts', rec); } catch (e) { console.warn('Saving the layout failed.', e); }
    }
    writing = false;
  }

  // ---- floorplans ----
  const getFloorplan = id => db ? db.get('floorplans', id) : Promise.resolve(id === DEFAULT_PLAN.id ? DEFAULT_PLAN : undefined);
  const listFloorplans = () => db ? db.getAll('floorplans') : Promise.resolve([DEFAULT_PLAN]);

  return { init, loadLayout, saveLayout, getFloorplan, listFloorplans, DEFAULT_PLAN_ID: DEFAULT_PLAN.id };
})();
