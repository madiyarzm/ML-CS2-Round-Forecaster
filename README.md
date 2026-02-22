# CS2-Economic-Predictor: Modeling Tactical Asymmetry

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Scikit-Learn](https://img.shields.io/badge/machine--learning-Scikit--Learn-orange.svg)
![Selenium](https://img.shields.io/badge/web--scraping-Selenium-green.svg)

A Machine Learning project that analyzes personal Counter-Strike 2 match history to predict round outcomes based on economic state and opening engagement data.

---

## 📌 Project Overview
In competitive *Counter-Strike 2*, resources are everything. This project investigates the hypothesis: **Is the economic asymmetry at the start of a round the strongest predictor of its outcome?**

By decomposing matches into discrete rounds, I extracted telemetry from **424 rounds** of play to build a Logistic Regression model that balances "Value Gaps" (equipment cost) against "First Kills" (tactical momentum).

## Technical Stack
* **Data Collection:** Python + Selenium (Automated scraping of player telemetry from `csstats.gg`).
* **Data Processing:** Pandas & NumPy (Filtering, normalization, and feature engineering).
* **Machine Learning:** Scikit-Learn (Logistic Regression with 5-Fold Cross-Validation).
* **Visualization:** Matplotlib & Seaborn (Heatmaps, Boxplots, Confusion Matrices, and ROC Curves).

## Key Findings
* **Model Accuracy:** **68.24%** on unseen test data—a high predictive rate for a chaotic tactical environment.
* **The "First Kill" Multiplier:** Securing the first kill ($0.38$ correlation) proved significantly more influential than having a raw equipment lead ($0.16$ correlation).
* **Stable Logic:** A 5-fold cross-validation standard deviation of only **5.75%** confirms that the model's logic is consistent across different maps and match contexts.



## How it Works
1.  **Scraping:** The `scraper.py` script automates a browser to navigate match histories, expanding round details to extract economic and kill-feed data.
2.  **Engineering:** Raw team cash and equipment values are merged into a single `value_gap` feature ($Value_{CT} - Value_{T}$).
3.  **Modeling:** A Logistic Regression classifier uses the **Sigmoid function** to calculate win probability.
    $$\sigma(z) = \frac{1}{1 + e^{-z}}$$
4.  **Evaluation:** Success is measured through **Confusion Matrices** and **ROC-AUC curves** to separate systemic wins from "tactical upsets."



## 📂 Repository Structure
* `ML_assignment.ipynb`: The complete notebook containing EDA, training, and evaluation.
* `cs2_final_clean_data.csv`: The processed dataset of 424 round observations.
* `scraper/`: (Optional) Python scripts for the Selenium automation pipeline.
* `requirements.txt`: List of necessary Python libraries.

## ⚙️ Installation
To run this project locally:
1. Clone the repo: `git clone https://github.com/your-username/your-repo-name.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Launch the notebook: `jupyter notebook ML_assignment.ipynb`