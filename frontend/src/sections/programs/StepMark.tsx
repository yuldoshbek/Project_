/**
 * Ступень словом и отклонение рядом — так же, как на Пульте и в плитке проекта: сигнал с
 * названием ступени, число дней — отдельной подписью. Одна ступень выглядит одинаково на
 * горизонте, плитке, в карточке и в «до конца года».
 */

import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL, type Step } from '@/sections/pult/model';
import { deviationText } from '@/sections/pult/text';
import { Signal } from '@/shared/ui/Signal';

export function StepMark({ step, deviation }: { step: Step; deviation: number }) {
  const { t } = useTranslation();
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <Signal state={STEP_SIGNAL[step]}>{t(`pult.steps.${step}`)}</Signal>
      <span className="numeric text-xs font-medium text-ink">
        {deviationText(t, { step, deviation })}
      </span>
    </span>
  );
}
