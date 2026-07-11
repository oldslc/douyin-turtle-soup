import { cn } from '@/lib/utils';
import type { ReactNode, HTMLAttributes } from 'react';

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  variant?: 'default' | 'primary' | 'secondary' | 'accent';
  glow?: boolean;
}

/**
 * 玻璃拟态卡片组件
 * 提供毛玻璃效果和发光边框
 */
export function GlassCard({
  children,
  className,
  variant = 'default',
  glow = false,
  ...props
}: GlassCardProps) {
  const variantStyles = {
    default: 'bg-background/40 border-border/50',
    primary: 'bg-primary/10 border-primary/30',
    secondary: 'bg-secondary/10 border-secondary/30',
    accent: 'bg-accent/10 border-accent/30',
  };

  const glowStyles = glow
    ? {
        default: 'shadow-[0_0_20px_rgba(var(--foreground-rgb),0.1)]',
        primary: 'shadow-[0_0_20px_rgba(var(--primary-rgb),0.3)]',
        secondary: 'shadow-[0_0_20px_rgba(var(--secondary-rgb),0.3)]',
        accent: 'shadow-[0_0_20px_rgba(var(--accent-rgb),0.3)]',
      }[variant]
    : '';

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-xl border backdrop-blur-md transition-all duration-300',
        variantStyles[variant],
        glowStyles,
        className
      )}
      {...props}
    >
      {/* 玻璃反光效果 */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
      
      {/* 内容 */}
      <div className="relative z-10 h-full">{children}</div>
    </div>
  );
}
