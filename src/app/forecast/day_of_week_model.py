import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import mean_absolute_error, r2_score

# --- Load Data ---
df = pd.read_excel(r"C:\Users\bkuhn\Downloads\GPA Gate Transactions by Day.xlsx", parse_dates=["Date"])

df["day_of_week"] = df["Date"].dt.day_name()

# --- Encode Day of Week ---
encoder = OneHotEncoder(sparse_output=False, drop="first")  # drop="first" avoids multicollinearity
X = encoder.fit_transform(df[["day_of_week"]])
y = df["Records"].values

# --- Train Model ---
model = LinearRegression()
model.fit(X, y)

# --- Evaluate ---
y_pred = model.predict(X)
mae = mean_absolute_error(y, y_pred)
r2 = r2_score(y, y_pred)

print(f"MAE:  {mae:,.1f} transactions")
print(f"R²:   {r2:.3f}")

# --- Inspect Coefficients ---
feature_names = encoder.get_feature_names_out(["day_of_week"])
coef_df = pd.DataFrame({
    "feature": feature_names,
    "coefficient": model.coef_
}).sort_values("coefficient", ascending=False)

print(f"\nIntercept (baseline day): {model.intercept_:,.1f}")
print(coef_df.to_string(index=False))

# --- Predict for a New Day ---
def predict_for_day(day_name: str) -> float:
    X_new = encoder.transform([[day_name]])
    return model.predict(X_new)[0]

# Example
for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
    print(f"{day}: {predict_for_day(day):,.0f} predicted transactions")