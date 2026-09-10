install.packages("TH.data")
library(TH.data)
data("GBSG2", package = "TH.data")

# 1. Data Summary
dim(GBSG2)      ## 686 x 10
str(GBSG2)
summary(GBSG2)
table(GBSG2$cens)     ## 0 = 删失； 1 = 复发事件                    
table(GBSG2$horTh)    ## 激素治疗分组人数
table(GBSG2$tgrade)   ## 肿瘤分级分布

# 2. Research Questions
## Q1: What is the effect of hormone therapy on recurrence-free survival?
  ## Clue: (Does KM Curve fork? Univariate HR = , p = )
  ## Proposed Method: Cox PH, adjust
  ## Checkpoint: HR/95%CI/p-value/PH inspection
### 2.1.1 KM Curve：按激素治疗分组，看两条曲线分不分叉
library(survival)
library(survminer)

fit_km <- survfit(Surv(time, cens) ~ horTh, data = GBSG2)
summary(fit_km)
ggsurvplot(fit_km, pval = TRUE, risk.table = TRUE)

### 2.1.2 Univariable Scanning
vars <- c("age", "tsize", "pnodes", "estrec", "progrec", "menostat", "tgrade")
for (v in vars) {
  cat("=====", v, "=====\n")
  f <- as.formula(paste("Surv(time, cens) ~", v))
  print(summary(coxph(f, data = GBSG2))$coefficients[, c("exp(coef)", "Pr(>|z|)")])
}

## 2.2 Main Analysis: Multivariate Cox + PH Hypothetical Diagnosis
### 2.2.1 Multivariate Cox：horTh adjusted with all covariates
m2 <- coxph(Surv(time, cens) ~ horTh + age + tsize + pnodes +
              estrec + progrec + menostat + tgrade, data = GBSG2)
summary(m2)   #### coef / exp(coef)=HR / se / z / p

hr_ci <- cbind(exp(coef(m2)), exp(confint(m2)))   #### HR 与 95% CI
colnames(hr_ci) <- c("HR", "CI_low", "CI_high")
round(hr_ci, 3)

zph <- cox.zph(m2)    #### PH Hypothesis Test（Schoenfeld Residual）
print(zph)
plot(zph, var = "horTh")   #### Residual trend chart of horTh

## Q2: 
summary(coxph(Surv(time, cens) ~ horTh, data = GBSG2))  
### horTh Univariate HR → original or adjusted = amplitude of mixing
cor(GBSG2$estrec, GBSG2$progrec, method = "spearman")   
### estrec↔progrec related → multicollinearity hypothesis

## Q4: Sensitivity Analysis：Stratification of covariates of PH violations,
## Verifying the robustness of horTh HR
m_strat <- coxph(Surv(time, cens) ~ horTh + age + tsize + pnodes +
                   estrec + progrec + strata(menostat, tgrade), data = GBSG2)
summary(m_strat)

## Q3：'tgrade' Comparison of Encoding Methods (Linear vs. Factor vs. Orthogonal Polynomial)
GBSG2$tgrade_num <- as.numeric(GBSG2$tgrade)
base <- "Surv(time, cens) ~ horTh + age + tsize + pnodes + estrec + progrec + menostat + "

m_lin  <- coxph(as.formula(paste0(base, "tgrade_num")), data = GBSG2)
m_fac  <- coxph(as.formula(paste0(base, "tgrade")), data = GBSG2)
m_poly <- coxph(as.formula(paste0(base, "poly(as.numeric(tgrade), 2)")), data = GBSG2)

### Three Model Fits (AIC: Lower is Better)
c(linear_AIC = AIC(m_lin), factor_AIC = AIC(m_fac), poly_AIC = AIC(m_poly))

### Linear against Factor (nested model likelihood ratio test 
###s.t. significant indicating linear coding loss information)
anova(m_lin, m_fac)

## Q5: Survival Random Forest against Cox (C-index)
library(ranger)

set.seed(42)
rf_fit <- ranger(Surv(time, cens) ~ horTh + age + tsize + pnodes +
                   estrec + progrec + menostat + tgrade,
                 data = GBSG2,
                 num.trees = 500,
                 respect.unordered.factors = TRUE,
                 importance = "permutation")

### prediction.error in Survival Model = 1 - Harrell's C（OOB Consistency）
c_rsf <- 1 - rf_fit$prediction.error
cat("ranger OOB C-index =", round(c_rsf, 3), "（Cox 的 C-index = 0.692）\n")

### Variable Importance
print(round(importance(rf_fit), 4))