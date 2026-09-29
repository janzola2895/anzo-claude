// ANZO's visual orb: a Three.js particle sphere reacting to voice state.
// Loaded as an ES module (see the importmap in index.html); bridges to the
// classic-script app.js via window.setOrbState so app.js doesn't need to
// become a module itself. Purely decorative -- if this fails to load (CDN
// down, no WebGL), app.js's setOrb() guards the call and everything else
// keeps working, and the CSS aura in style.css still glows behind it.
//
// No visible edges, on purpose: the canvas covers the whole window (the old
// 220px square clipped the sphere whenever it pulsed past its own bounds),
// particles are soft round sprites blended additively, and the glow sprites
// fall off to fully transparent before reaching the window edge.

import * as THREE from "three";

const STATES = {
  idle:      { color: 0x5b7cff, opacity: 0.55, rotSpeed: 0.06, pulseSpeed: 1.1, pulseAmp: 0.025, core: 0.22, halo: 0.30 },
  listening: { color: 0x66a3ff, opacity: 0.90, rotSpeed: 0.14, pulseSpeed: 2.2, pulseAmp: 0.05,  core: 0.45, halo: 0.50 },
  working:   { color: 0xffb03b, opacity: 0.90, rotSpeed: 0.30, pulseSpeed: 5.7, pulseAmp: 0.07,  core: 0.55, halo: 0.55 },
  speaking:  { color: 0x3bffaa, opacity: 0.95, rotSpeed: 0.35, pulseSpeed: 9.0, pulseAmp: 0.10,  core: 0.65, halo: 0.60 },
};

const canvas = document.getElementById("orb-canvas");
const RADIUS = 1.6;
const R_MAX = RADIUS * 1.5 * 1.12; // outer shell x biggest pulse
const FOV = 40;
const CENTER_Y = 0.38; // orb centre, as a fraction of window height from the top

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0x000000, 0);

// Soft round sprite: bright centre falling to fully transparent.
function radialTexture(stops) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (const [at, alpha] of stops) grad.addColorStop(at, `rgba(255,255,255,${alpha})`);
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}
const dotTexture = radialTexture([[0, 1], [0.35, 0.65], [1, 0]]);
const glowTexture = radialTexture([[0, 1], [0.12, 0.62], [0.28, 0.3], [0.45, 0.12], [0.62, 0.04], [0.8, 0.008], [1, 0]]);

function shell(count, rMin, rMax, size, opacityScale) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const theta = 2 * Math.PI * Math.random();
    const phi = Math.acos(2 * Math.random() - 1);
    const r = RADIUS * (rMin + Math.random() * (rMax - rMin));
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
    const b = 0.35 + Math.random() * 0.65; // per-particle brightness
    colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = b;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    map: dotTexture,
    size,
    sizeAttenuation: true,
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geometry, material);
  points.userData.opacityScale = opacityScale;
  return points;
}

const group = new THREE.Group();
const inner = shell(900, 0.92, 1.08, 0.13, 1.0);
const outer = shell(260, 1.25, 1.5, 0.08, 0.55);
group.add(inner, outer);
scene.add(group);

function glowSprite(scale) {
  const mat = new THREE.SpriteMaterial({
    map: glowTexture, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(scale, scale, 1);
  return sprite;
}
const core = glowSprite(RADIUS * 2.6);
const halo = glowSprite(RADIUS * 3.6);
group.add(halo, core);

// Every value eases toward the target state instead of snapping, so state
// changes read as smooth transitions rather than jump-cuts.
let target = STATES.idle;
const current = { ...STATES.idle };
const currentColor = new THREE.Color(current.color);
const targetColor = new THREE.Color(current.color);
const LERP = 0.06;
const lerp = (a, b, t) => a + (b - a) * t;

export function setOrbState(name) {
  target = STATES[name] || STATES.idle;
  targetColor.set(target.color);
}

// Size the camera so the biggest possible extent of the sphere (outer shell at
// full pulse) fits a circle of ~34% of the window's short side, and sits at
// CENTER_Y. Recomputed on resize, so any window size keeps the whole orb and
// its halo inside the frame.
function layout() {
  const w = Math.max(1, canvas.clientWidth);
  const h = Math.max(1, canvas.clientHeight);
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  const tan = Math.tan((FOV * Math.PI) / 360);
  const radiusPx = 0.34 * Math.min(w, h);
  camera.position.z = (R_MAX * h) / (2 * radiusPx * tan);
  camera.updateProjectionMatrix();
  // NDC y of the centre -> world y at z = 0
  group.position.y = (1 - 2 * CENTER_Y) * camera.position.z * tan;
}
layout();
window.addEventListener("resize", layout);

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  const t = clock.elapsedTime;

  for (const k of ["opacity", "rotSpeed", "pulseSpeed", "pulseAmp", "core", "halo"]) {
    current[k] = lerp(current[k], target[k], LERP);
  }
  currentColor.lerp(targetColor, LERP);

  const pulse = 1 + Math.sin(t * current.pulseSpeed) * current.pulseAmp;

  for (const p of [inner, outer]) {
    p.material.color.copy(currentColor);
    p.material.opacity = current.opacity * p.userData.opacityScale;
  }
  inner.rotation.y += current.rotSpeed * dt;
  inner.rotation.x += current.rotSpeed * 0.35 * dt;
  outer.rotation.y -= current.rotSpeed * 0.6 * dt;
  outer.rotation.z += current.rotSpeed * 0.25 * dt;

  core.material.color.copy(currentColor);
  halo.material.color.copy(currentColor);
  core.material.opacity = current.core * (0.85 + 0.15 * Math.sin(t * current.pulseSpeed));
  halo.material.opacity = current.halo;

  group.scale.setScalar(pulse);
  renderer.render(scene, camera);
}

animate();

window.setOrbState = setOrbState;
