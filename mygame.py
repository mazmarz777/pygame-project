"""
Cosmic Salvage - compact single-file edition
Controls: WASD/Arrows move, SPACE shoot, P pause, R restart, ENTER start, ESC quit
Run: python cosmic_salvage.py
"""

import random, sys, math, pygame

# ---------- constants ----------
WIDTH, HEIGHT, FPS, TITLE = 900, 650, 60, "Cosmic Salvage"
BLACK, WHITE, GREY = (8,10,20), (240,240,245), (120,120,130)
RED, GREEN, BLUE = (220,60,60), (70,220,120), (70,140,220)
YELLOW, PURPLE, CYAN, ORANGE = (240,210,70), (170,90,220), (80,220,220), (240,140,60)

PLAYER_SPEED, PLAYER_MAX_HP, PLAYER_SIZE = 6, 5, 22
FIRE_CD, RAPID_CD, INVULN_MS = 300, 100, 1500
BULLET_SPEED, BULLET_R = 11, 4
AST_SIZES = {"large": 46, "medium": 30, "small": 16}
AST_HP = {"large": 3, "medium": 2, "small": 1}
SPAWN_START, SPAWN_MIN = 1100, 350
CRYSTAL_DROP, POWERUP_DROP = 0.55, 0.12
CRYSTAL_VALUE, MAGNET_R, CRYSTAL_SPEED = 10, 160, 2.5
POWERUP_SPEED, POWERUP_MS = 2.0, 7000
POWERUP_TYPES = ["shield", "rapidfire", "health", "magnet"]
SCORE_PER_LEVEL, PARTICLE_MS = 300, 500


def text(surf, s, size, x, y, color=WHITE, center=True):
    f = pygame.font.Font(None, size)
    r = f.render(s, True, color)
    rect = r.get_rect(center=(x, y)) if center else r.get_rect(topleft=(x, y))
    surf.blit(r, rect)


class SoundBank:
    """Synthesized SFX; disables itself silently if numpy/mixer unavailable."""
    def __init__(self):
        self.enabled, self.sounds = False, {}
        try:
            import numpy as np
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1)
            self.np, self.enabled = np, True
            self.sounds = {
                "shoot": self._tone(880, 80, .15), "explosion": self._tone(120, 220, .35),
                "powerup": self._tone(660, 180, .25), "hit": self._tone(200, 250, .35),
                "gameover": self._tone(140, 600, .3),
            }
        except Exception:
            self.enabled = False

    def _tone(self, freq, ms, vol):
        np = self.np
        n = int(44100 * ms / 1000)
        t = np.linspace(0, ms / 1000, n, False)
        wave = np.sin(freq * t * 2 * np.pi) * np.linspace(1, 0, n)
        return pygame.sndarray.make_sound((wave * vol * 32767).astype(np.int16))

    def play(self, name):
        if self.enabled and name in self.sounds:
            try: self.sounds[name].play()
            except Exception: pass


class Particle:
    """Fading drifting dot for explosion/pickup bursts."""
    def __init__(self, x, y, color, speed=(1, 4), life=PARTICLE_MS, r=(2, 4)):
        a, s = random.uniform(0, 6.283), random.uniform(*speed)
        self.vx, self.vy = math.cos(a) * s, math.sin(a) * s
        self.x, self.y, self.color = x, y, color
        self.life, self.age, self.r = life, 0, random.uniform(*r)

    def update(self, dt):
        self.x += self.vx; self.y += self.vy
        self.vx *= .96; self.vy *= .96
        self.age += dt or 16
        return self.age < self.life

    def draw(self, s):
        r = self.r * max(0, 1 - self.age / self.life)
        if r > .5: pygame.draw.circle(s, self.color, (int(self.x), int(self.y)), int(r))


def burst(particles, x, y, color, n=18, speed=(1, 5)):
    particles += [Particle(x, y, color, speed) for _ in range(n)]


class Bullet:
    def __init__(self, x, y):
        self.x, self.y, self.r, self.alive = x, y, BULLET_R, True

    def update(self):
        self.y -= BULLET_SPEED
        if self.y < -20: self.alive = False

    def draw(self, s):
        pygame.draw.circle(s, CYAN, (int(self.x), int(self.y)), self.r)
        pygame.draw.circle(s, WHITE, (int(self.x), int(self.y)), max(1, self.r - 2))

    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r * 2, self.r * 2)


class Crystal:
    """Score pickup; drifts toward player when magnet power-up is active."""
    def __init__(self, x, y):
        self.x, self.y, self.r, self.alive, self.a = x, y, 6, True, 0.0

    def update(self, player, magnet):
        self.a += 6
        if magnet:
            dx, dy = player.x - self.x, player.y - self.y
            d = math.hypot(dx, dy)
            if d < MAGNET_R and d > 1:
                self.x += dx / d * 6; self.y += dy / d * 6
            else:
                self.y += CRYSTAL_SPEED
        else:
            self.y += CRYSTAL_SPEED
        if self.y > HEIGHT + 20: self.alive = False

    def draw(self, s):
        pts = [(self.x + math.cos(math.radians(self.a + i * 90)) * self.r,
                self.y + math.sin(math.radians(self.a + i * 90)) * self.r) for i in range(4)]
        pygame.draw.polygon(s, YELLOW, pts)

    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r * 2, self.r * 2)


class PowerUp:
    COLORS = {"shield": BLUE, "rapidfire": ORANGE, "health": GREEN, "magnet": PURPLE}
    LABELS = {"shield": "S", "rapidfire": "R", "health": "+", "magnet": "M"}

    def __init__(self, x, y, kind=None):
        self.x, self.y = x, y
        self.kind = kind or random.choice(POWERUP_TYPES)
        self.r, self.alive = 12, True

    def update(self):
        self.y += POWERUP_SPEED
        if self.y > HEIGHT + 20: self.alive = False

    def draw(self, s):
        pygame.draw.circle(s, self.COLORS[self.kind], (int(self.x), int(self.y)), self.r)
        pygame.draw.circle(s, WHITE, (int(self.x), int(self.y)), self.r, 2)
        text(s, self.LABELS[self.kind], 16, self.x, self.y, WHITE)

    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r * 2, self.r * 2)


class Asteroid:
    """Splits large->medium->small on destruction; irregular rocky shape."""
    def __init__(self, x, y, size="large", vx=0.0):
        self.size, self.x, self.y = size, x, y
        self.r = AST_SIZES[size]
        self.hp = self.max_hp = AST_HP[size]
        self.vy = 2.0 + random.uniform(0, 1.2)
        self.vx = vx
        self.rot, self.spin, self.alive = random.uniform(0, 360), random.uniform(-2, 2), True
        self.shape = [((360 / 9) * i, self.r * random.uniform(.75, 1.05)) for i in range(9)]

    def update(self):
        self.y += self.vy; self.x += self.vx; self.rot += self.spin
        if self.x < self.r: self.x, self.vx = self.r, -self.vx
        if self.x > WIDTH - self.r: self.x, self.vx = WIDTH - self.r, -self.vx
        if self.y - self.r > HEIGHT: self.alive = False

    def hit(self, dmg=1):
        self.hp -= dmg
        return self.hp <= 0

    def child_size(self):
        return {"large": "medium", "medium": "small"}.get(self.size)

    def draw(self, s):
        pts = [(self.x + math.cos(math.radians(a + self.rot)) * r,
                self.y + math.sin(math.radians(a + self.rot)) * r) for a, r in self.shape]
        pygame.draw.polygon(s, GREY, pts)
        pygame.draw.polygon(s, WHITE, pts, 2)
        if self.hp < self.max_hp:
            pygame.draw.circle(s, ORANGE, (int(self.x), int(self.y)), 3)

    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r * 2, self.r * 2)


class Player:
    def __init__(self, x, y):
        self.x, self.y, self.speed = x, y, PLAYER_SPEED
        self.hp = self.max_hp = PLAYER_MAX_HP
        self.size = PLAYER_SIZE
        self.last_shot = self.invuln_until = 0
        self.buffs, self.alive = {}, True

    def input(self, keys):
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        if dx and dy: dx *= .7071; dy *= .7071
        self.x = max(self.size, min(WIDTH - self.size, self.x + dx * self.speed))
        self.y = max(self.size, min(HEIGHT - self.size, self.y + dy * self.speed))

    def can_shoot(self, now):
        cd = RAPID_CD if self.has("rapidfire") else FIRE_CD
        return now - self.last_shot >= cd

    def shoot(self, now):
        self.last_shot = now
        return Bullet(self.x, self.y - self.size)

    def apply(self, kind, now):
        if kind == "health": self.hp = min(self.max_hp, self.hp + 2)
        else: self.buffs[kind] = now + POWERUP_MS

    def has(self, kind): return kind in self.buffs

    def tick_buffs(self, now):
        for k in [k for k, t in self.buffs.items() if now >= t]: del self.buffs[k]

    def invulnerable(self, now): return now < self.invuln_until or self.has("shield")

    def hit(self, dmg, now):
        if self.invulnerable(now): return False
        self.hp -= dmg
        self.invuln_until = now + INVULN_MS
        if self.hp <= 0: self.hp, self.alive = 0, False
        return True

    def draw(self, s, now):
        color = GREY if self.invulnerable(now) and (now // 100) % 2 == 0 else CYAN
        tip, l, r = (self.x, self.y - self.size), (self.x - self.size * .75, self.y + self.size * .7), \
                    (self.x + self.size * .75, self.y + self.size * .7)
        pygame.draw.polygon(s, color, [tip, l, r])
        pygame.draw.polygon(s, WHITE, [tip, l, r], 2)
        pygame.draw.polygon(s, ORANGE, [(self.x - 6, self.y + self.size * .7),
                                         (self.x + 6, self.y + self.size * .7),
                                         (self.x, self.y + self.size * 1.2)])
        if self.has("shield"):
            pygame.draw.circle(s, BLUE, (int(self.x), int(self.y)), int(self.size + 10), 2)

    def rect(self):
        return pygame.Rect(self.x - self.size * .6, self.y - self.size * .6, self.size * 1.2, self.size * 1.2)


class Starfield:
    """Procedural multi-layer parallax stars."""
    def __init__(self, layers=3, n=45):
        self.layers = [{"speed": .6 + i * .9, "size": 1 + i,
                         "stars": [[random.uniform(0, WIDTH), random.uniform(0, HEIGHT)] for _ in range(n)]}
                        for i in range(layers)]

    def update(self):
        for layer in self.layers:
            for st in layer["stars"]:
                st[1] += layer["speed"]
                if st[1] > HEIGHT: st[1], st[0] = 0, random.uniform(0, WIDTH)

    def draw(self, s):
        for layer in self.layers:
            for st in layer["stars"]:
                pygame.draw.circle(s, WHITE, (int(st[0]), int(st[1])), layer["size"])


class HUD:
    def draw(self, s, score, level, player, now):
        text(s, f"Score: {score}", 24, 90, 24, WHITE, False)
        text(s, f"Level: {level}", 20, 90, 52, YELLOW, False)
        w, h, x, y = 160, 16, WIDTH - 180, 20
        pygame.draw.rect(s, GREY, (x, y, w, h), border_radius=4)
        fill = int(w * (player.hp / player.max_hp))
        color = GREEN if player.hp > player.max_hp * .5 else (YELLOW if player.hp > player.max_hp * .25 else RED)
        pygame.draw.rect(s, color, (x, y, fill, h), border_radius=4)
        pygame.draw.rect(s, WHITE, (x, y, w, h), 2, border_radius=4)
        text(s, "HULL", 12, x + w / 2, y + h / 2, WHITE)
        for i, (k, t) in enumerate(player.buffs.items()):
            text(s, f"{k.upper()}: {max(0,(t-now)/1000):0.1f}s", 16, WIDTH - 90, 50 + i * 20, CYAN)


MENU, PLAYING, PAUSED, GAMEOVER = "menu", "playing", "paused", "gameover"


class Game:
    """State machine + spawning + collisions + main loop."""
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.sounds, self.stars, self.hud = SoundBank(), Starfield(), HUD()
        self.state = MENU
        self.reset()

    def reset(self):
        self.player = Player(WIDTH // 2, HEIGHT - 80)
        self.bullets, self.asteroids, self.crystals, self.powerups, self.particles = [], [], [], [], []
        self.score, self.level = 0, 1
        self.spawn_iv = SPAWN_START
        self.last_spawn = pygame.time.get_ticks()

    def spawn_asteroid(self):
        self.asteroids.append(Asteroid(random.uniform(50, WIDTH - 50), -50, "large", random.uniform(-1, 1)))

    def split(self, a):
        child = a.child_size()
        if child:
            for side in (-1, 1):
                self.asteroids.append(Asteroid(a.x, a.y, child, side * random.uniform(1, 2.5)))
        if random.random() < CRYSTAL_DROP: self.crystals.append(Crystal(a.x, a.y))
        if random.random() < POWERUP_DROP: self.powerups.append(PowerUp(a.x, a.y))

    def update(self):
        now = pygame.time.get_ticks()
        self.stars.update()
        if self.state != PLAYING: return

        keys = pygame.key.get_pressed()
        self.player.input(keys)
        self.player.tick_buffs(now)
        if keys[pygame.K_SPACE] and self.player.can_shoot(now):
            self.bullets.append(self.player.shoot(now))
            self.sounds.play("shoot")

        lvl = 1 + self.score // SCORE_PER_LEVEL
        if lvl != self.level:
            self.level = lvl
            self.spawn_iv = max(SPAWN_MIN, SPAWN_START - (lvl - 1) * 80)
        if now - self.last_spawn >= self.spawn_iv:
            self.spawn_asteroid(); self.last_spawn = now

        for b in self.bullets: b.update()
        self.bullets = [b for b in self.bullets if b.alive]
        for a in self.asteroids: a.update()
        self.asteroids = [a for a in self.asteroids if a.alive]
        magnet = self.player.has("magnet")
        for c in self.crystals: c.update(self.player, magnet)
        self.crystals = [c for c in self.crystals if c.alive]
        for p in self.powerups: p.update()
        self.powerups = [p for p in self.powerups if p.alive]
        self.particles = [p for p in self.particles if p.update(self.clock.get_time())]

        self._collisions(now)
        if not self.player.alive:
            self.state = GAMEOVER
            self.sounds.play("gameover")

    def _collisions(self, now):
        for b in self.bullets:
            if not b.alive: continue
            for a in self.asteroids:
                if a.alive and b.alive and b.rect().colliderect(a.rect()):
                    b.alive = False
                    if a.hit(1):
                        a.alive = False
                        self.score += {"large": 20, "medium": 35, "small": 50}[a.size]
                        burst(self.particles, a.x, a.y, ORANGE, 22)
                        self.sounds.play("explosion")
                        self.split(a)
                    break

        pr = self.player.rect()
        for a in self.asteroids:
            if a.alive and pr.colliderect(a.rect()):
                dmg = {"large": 2, "medium": 1, "small": 1}[a.size]
                if self.player.hit(dmg, now):
                    self.sounds.play("hit")
                    burst(self.particles, self.player.x, self.player.y, RED, 14)
                a.alive = False
                burst(self.particles, a.x, a.y, GREY, 10)

        for c in self.crystals:
            if c.alive and pr.colliderect(c.rect()):
                c.alive = False; self.score += CRYSTAL_VALUE
                burst(self.particles, c.x, c.y, YELLOW, 8, (.5, 2))

        for p in self.powerups:
            if p.alive and pr.colliderect(p.rect()):
                p.alive = False
                self.player.apply(p.kind, now)
                self.sounds.play("powerup")
                burst(self.particles, p.x, p.y, PowerUp.COLORS[p.kind], 16)

    def draw(self):
        self.screen.fill(BLACK)
        self.stars.draw(self.screen)
        if self.state == MENU:
            self._menu()
        else:
            for group in (self.crystals, self.powerups, self.asteroids, self.bullets, self.particles):
                for obj in group: obj.draw(self.screen)
            if self.player.alive: self.player.draw(self.screen, pygame.time.get_ticks())
            self.hud.draw(self.screen, self.score, self.level, self.player, pygame.time.get_ticks())
            if self.state == PAUSED: self._banner("PAUSED", "Press P to resume")
            elif self.state == GAMEOVER: self._banner("GAME OVER", f"Score: {self.score}   |   Press R to restart")
        pygame.display.flip()

    def _menu(self):
        text(self.screen, TITLE, 52, WIDTH / 2, HEIGHT / 2 - 90, CYAN)
        text(self.screen, "Dodge and destroy asteroids. Collect crystals. Survive.", 20, WIDTH / 2, HEIGHT / 2 - 30)
        text(self.screen, "WASD/Arrows: Move   SPACE: Shoot", 18, WIDTH / 2, HEIGHT / 2 + 10, GREY)
        text(self.screen, "P: Pause   R: Restart   ESC: Quit", 18, WIDTH / 2, HEIGHT / 2 + 36, GREY)
        text(self.screen, "Press ENTER to start", 24, WIDTH / 2, HEIGHT / 2 + 90, YELLOW)

    def _banner(self, title, sub):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        text(self.screen, title, 48, WIDTH / 2, HEIGHT / 2 - 20)
        text(self.screen, sub, 22, WIDTH / 2, HEIGHT / 2 + 30, YELLOW)

    def run(self):
        while True:
            self.clock.tick(FPS)
            for e in pygame.event.get():
                if e.type == pygame.QUIT: pygame.quit(); sys.exit()
                if e.type == pygame.KEYDOWN: self._key(e.key)
            self.update()
            self.draw()

    def _key(self, k):
        if k == pygame.K_RETURN and self.state == MENU: self.reset(); self.state = PLAYING
        elif k == pygame.K_p and self.state in (PLAYING, PAUSED):
            self.state = PAUSED if self.state == PLAYING else PLAYING
        elif k == pygame.K_r and self.state == GAMEOVER: self.reset(); self.state = PLAYING
        elif k == pygame.K_ESCAPE: pygame.quit(); sys.exit()


if __name__ == "__main__":
    Game().run()