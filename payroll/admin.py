from django.contrib import admin

from .models import (
    CalculationBasis,
    CalculationBasisAdvantage,
    PayrollConfiguration,
    Salary,
    SalaryAdvantage,
    SalaryDeduction,
)

admin.site.register(PayrollConfiguration)
admin.site.register(CalculationBasis)
admin.site.register(CalculationBasisAdvantage)
admin.site.register(Salary)
admin.site.register(SalaryAdvantage)
admin.site.register(SalaryDeduction)
