import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

/**
 * FiscAudit Pro — strict monochrome theme.
 *
 * Brand colour tokens (navy, gold, amber, primary, brand) are intentionally
 * collapsed to the monochrome scale. Existing components that reference
 * `bg-navy`, `bg-gold`, `text-navy-deep`, `hover:bg-amber-500`, etc. will
 * continue to compile — they just resolve to pure black / ink shades. UI
 * hierarchy is now expressed via typographic weight, outlines, and pip
 * iconography (●○○ / ●●○ / ●●●), not hue.
 */
const config: Config = {
  darkMode: ['class'],
  content: ['./src/**/*.{ts,tsx,mdx}'],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: { '2xl': '1440px' },
    },
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Plus Jakarta Sans', 'Inter', 'sans-serif'],
      },
      fontWeight: {
        // Heading weights bumped up — weight replaces colour for hierarchy.
        heading: '700',
        display: '800',
      },
      colors: {
        // -----------------------------------------------------------------
        // Monochrome scale — the only palette in the app.
        // -----------------------------------------------------------------
        'pure-black': '#000000',
        'pure-white': '#FFFFFF',
        ink: {
          50: '#FAFAFA',
          100: '#E5E5E5',
          200: '#D4D4D4',
          300: '#A3A3A3',
          500: '#737373',
          700: '#404040',
          800: '#171717',
          900: '#0A0A0A',
          DEFAULT: '#171717',
        },

        // -----------------------------------------------------------------
        // Legacy brand aliases — kept so existing classes still resolve,
        // but every shade collapses to the monochrome scale.
        // -----------------------------------------------------------------
        navy: {
          DEFAULT: '#000000',
          deep: '#000000',
          soft: '#171717',
        },
        gold: {
          DEFAULT: '#000000',
          soft: '#E5E5E5',
        },
        brand: {
          DEFAULT: '#000000',
          soft: '#171717',
        },
        // Tailwind's `amber-*` family is referenced directly in a few
        // components (e.g. `hover:bg-[#c4912e]`, `bg-amber-100`). We can't
        // override Tailwind's default `amber` from extend without a full
        // colour reset, so callers that use bracket notation will be
        // migrated in component pass. For the named-shade override path we
        // expose a flattened `amber` alias that points to black/ink.
        amber: {
          50: '#FAFAFA',
          100: '#E5E5E5',
          200: '#D4D4D4',
          300: '#A3A3A3',
          400: '#737373',
          500: '#000000',
          600: '#000000',
          700: '#171717',
          800: '#171717',
          900: '#0A0A0A',
        },

        // -----------------------------------------------------------------
        // Semantic risk aliases — semantics preserved, colour dropped.
        // Components should pair these with pip iconography + weight.
        // -----------------------------------------------------------------
        risk: {
          faible: '#404040', // ink-700
          moyen: '#404040',  // ink-700
          eleve: '#000000',  // pure-black
        },

        // -----------------------------------------------------------------
        // shadcn token bridge — drives every CSS-variable-backed colour.
        // -----------------------------------------------------------------
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        // Soft monochrome shadows — at most 4-6% black.
        'mono-sm': '0 1px 2px 0 rgb(0 0 0 / 0.04)',
        'mono': '0 2px 6px -1px rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.04)',
        'mono-lg': '0 8px 24px -6px rgb(0 0 0 / 0.06), 0 2px 6px -2px rgb(0 0 0 / 0.04)',
        'mono-hover': '0 10px 30px -8px rgb(0 0 0 / 0.08), 0 4px 10px -4px rgb(0 0 0 / 0.05)',
      },
    },
  },
  plugins: [animate],
};

export default config;
