// Damped springs - used by the AI core (smooth state morphing) and to
// generate the CSS spring easing curve used across the interface.

export class Spring {
  constructor(value, { stiffness = 60, damping = 14 } = {}) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.stiffness = stiffness;
    this.damping = damping;
  }

  step(dt) {
    // Semi-implicit Euler is stable at UI frame rates
    const force = -this.stiffness * (this.value - this.target) - this.damping * this.velocity;
    this.velocity += force * dt;
    this.value += this.velocity * dt;
    return this.value;
  }

  snap(value = this.target) {
    this.value = this.target = value;
    this.velocity = 0;
  }
}

/**
 * Simulates a spring's step response and returns it as a CSS linear()
 * easing, so CSS transitions get real spring physics (slight overshoot,
 * natural settle) instead of a bezier approximation.
 */
export function springEasing({ stiffness = 210, damping = 21, mass = 1, samples = 40 } = {}) {
  const dt = 1 / 600;
  let x = 0, v = 0, t = 0;
  const trace = [];
  while (t < 3) {
    const a = (-stiffness * (x - 1) - damping * v) / mass;
    v += a * dt;
    x += v * dt;
    t += dt;
    trace.push(x);
    if (t > 0.1 && Math.abs(x - 1) < 0.0015 && Math.abs(v) < 0.01) break;
  }
  const points = [];
  for (let i = 0; i <= samples; i++) {
    const idx = Math.min(trace.length - 1, Math.round((i / samples) * (trace.length - 1)));
    points.push(+trace[idx].toFixed(4));
  }
  points[points.length - 1] = 1;
  return { easing: `linear(0, ${points.slice(1).join(', ')})`, duration: Math.round(t * 1000) };
}

export function installSpringEasing() {
  if (!CSS.supports('transition-timing-function', 'linear(0, 1)')) return;
  const { easing, duration } = springEasing();
  const root = document.documentElement.style;
  root.setProperty('--ease-spring', easing);
  root.setProperty('--dur-spring', `${duration}ms`);
}
