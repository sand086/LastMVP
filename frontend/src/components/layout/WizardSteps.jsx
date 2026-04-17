import React from 'react';
import { CheckCircle2, ChevronRight } from 'lucide-react';

export const WizardSteps = ({ currentStep }) => (
    <div className="flex items-center gap-2 sm:gap-4 p-3 sm:p-4 bg-white border border-slate-200 rounded-sm overflow-x-auto">
        {[
            { num: 1, label: 'History Orders' },
            { num: 2, label: 'Route Summary' },
            { num: 3, label: 'Configurar y Crear' },
        ].map((step, i) => (
            <React.Fragment key={step.num}>
                {i > 0 && <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5 text-slate-300 flex-shrink-0" />}
                <div className={`flex items-center gap-2 flex-shrink-0 ${currentStep >= step.num ? 'text-slate-900' : 'text-slate-400'}`}>
                    <div className={`w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-xs sm:text-sm font-bold ${
                        currentStep > step.num ? 'bg-emerald-100 text-emerald-700' :
                        currentStep === step.num ? 'bg-slate-900 text-white' : 'bg-slate-200'
                    }`}>
                        {currentStep > step.num ? <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5" /> : step.num}
                    </div>
                    <span className="font-medium text-sm sm:text-base hidden sm:inline">{step.label}</span>
                    <span className="font-medium text-xs sm:hidden">{step.label.split(' ')[0]}</span>
                </div>
            </React.Fragment>
        ))}
    </div>
);
