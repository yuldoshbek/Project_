/**
 * Раздел, который наполняется в следующем блоке.
 *
 * Это не «заглушка со словом скоро». Здесь написано главное: **вопрос**, на который раздел
 * будет отвечать, и состав работ по плану. На приёмке блока 0 заказчик открывает любой
 * раздел и видит, что именно здесь будет и зачем, — а не пустой экран, по которому нельзя
 * понять, забыли раздел или он ещё не начат.
 */

import { useTranslation } from 'react-i18next';

import type { SectionDefinition } from '@/app/sections';
import { Card } from '@/shared/ui/Card';
import { Signal } from '@/shared/ui/Signal';

export function SoonSection({ section }: { section: SectionDefinition }) {
  const { t } = useTranslation();
  const Icon = section.icon;

  return (
    <div className="flex flex-col gap-4">
      {/* На телефоне метка встаёт своей строкой под заголовком. Рядом она сжимала вопрос
          раздела до двух слов в строку, и подпись читалась хуже, чем на мониторе. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
            <Icon className="size-5" />
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-ink-strong">{t(`sections.${section.id}`)}</h1>
            <p className="text-sm text-ink-muted">{t(`sectionQuestions.${section.id}`)}</p>
          </div>
        </div>
        <Signal className="self-start sm:ml-auto" state="wait">
          {t('soon.title', { block: section.block })}
        </Signal>
      </div>

      <Card title={t('soon.plan')} question={t(`sectionQuestions.${section.id}`)}>
        <p className="text-sm text-ink">{t('soon.body')}</p>
      </Card>
    </div>
  );
}
