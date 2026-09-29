// ANZO's visual orb: a Three.js particle sphere reacting to voice state.
// Loaded as an ES module (see the importmap in index.html); bridges to the
// classic-script app.js via window.setOrbState so app.js doesn't need to
// become a module itself. Purely decorative -- if this fails to load (CDN
// down, no WebGL), app.js's setOrb() guards the call and everything else
// keeps working.

import * as THREE from "three";

const STATES = {
  idle: { color: 0x5b7cff, opacity: 0.35, rotSpeed: 0.05, pulseSpeed: 0, pulseAmp: 0 },
  listening: { color: 0x5b7cff, opacity: 0.9, rotSpeed: 0.12, pulseSpeed: 0, pulseAmp: 0.05 },
  working: { color: 0xffb03b, opacity: 0.85, rotSpeed: 0.25, pulseSpeed: 5.7, pulseAmp: 0.09 },
  speaking: { color: 0x3bffaa, opacity: 0.95, rotSpeed: 0.35, pulseSpeed: 9.0, pulseAmp: 0.12 },
};

const canvas = document.getElementById("orb-canvas");
const size = canvas.clientWidth || 220;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
camera.position.z = 4.2;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setSize(size, size, false);

// Points scattered on a sphere SHELL (not a filled ball) -- jittered radius
// gives it depth instead of looking like a flat disc once rotating.
const PARTICLE_COUNT = 650;
const RADIUS = 1.6;
const positions = new Float32Array(PARTICLE_COUNT * 3);
for (let i = 0; i < PARTICLE_COUNT; i++) {
  const u = Math.random();
  const v = Math.random();
  const theta = 2 * Math.PI * u;
  const phi = Math.acos(2 * v - 1);
  const r = RADIUS * (0.92 + Math.random() * 0.16);
  positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
  positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
  positions[i * 3 + 2] = r * Math.cos(phi);
}
const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));

const material = new THREE.PointsMaterial({
  color: STATES.idle.color,
  size: 0.05,
  sizeAttenuation: true,
  transparent: true,
  opacity: STATES.idle.opacity,
  depthWrite: false,
});

const points = new THREE.Points(geometry, material);
scene.add(points);

// Current values lerp toward the target state's values every frame instead
// of snapping, so state changes (idle -> listening -> working -> speaking)
// read as smooth transitions rather than a jump-cut.
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

const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  const t = clock.elapsedTime;

  current.opacity = lerp(current.opacity, target.opacity, LERP);
  current.rotSpeed = lerp(current.rotSpeed, target.rotSpeed, LERP);
  current.pulseSpeed = lerp(current.pulseSpeed, target.pulseSpeed, LERP);
  current.pulseAmp = lerp(current.pulseAmp, target.pulseAmp, LERP);
  currentColor.lerp(targetColor, LERP);

  material.color.copy(currentColor);
  material.opacity = current.opacity;

  points.rotation.y += current.rotSpeed * dt;
  points.rotation.x += current.rotSpeed * 0.35 * dt;

  const pulse = current.pulseAmp > 0.001 ? 1 + Math.sin(t * current.pulseSpeed) * current.pulseAmp : 1;
  points.scale.setScalar(pulse);

  renderer.render(scene, camera);
}

animate();

window.addEventListener("resize", () => {
  const s = canvas.clientWidth || size;
  renderer.setSize(s, s, false);
});

window.setOrbState = setOrbState;
