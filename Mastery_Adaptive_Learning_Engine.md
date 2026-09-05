## Mastery

## An Adaptive Learning Engine that Models What a Student Knows

One-line Pitch: Instead of predicting a label, the system predicts a person's evolving knowledge state and then decides what to teach next — so classical ML, deep learning, NLP and reinforcement learning each become structurally necessary, not decorative.

## 1. Problem Statement

Online learning platforms deliver the same fixed sequence of content to every learner, and evaluate them only by a final score. This ignores two realities: a learner's mastery of a concept is a latent, time-varying quantity that must be inferred from noisy interaction data, and the optimal next question depends on that hidden state. Consequently learners are shown material that is either too easy (disengagement) or too hard (dropout), and instructors receive no early, interpretable signal about who is falling behind and on which specific concept.

This project proposes Mastery, an end-to-end adaptive learning engine that (i) infers a per-concept mastery probability for each learner from their sequential interaction history, (ii) segments learners into behavioural cohorts without supervision, (iii) understands free-text student answers and doubts in natural language, (iv) sequentially selects the next question to maximise long-term learning gain under an exploration–exploitation trade-off, and (v) explains every recommendation to the instructor. The system is trained on public interaction logs, validated against held-out learner trajectories, and deployed as a monitored web service with drift detection.

## 2. How It Covers the Full AI/ML Syllabus

| Module | What You Build | Syllabus Territory It Covers |
| --- | --- | --- |
| 1. Data & EDA | Ingest interaction logs, sessionise, engineer temporal + | Data preprocessing, feature engineering, imbalance |
|   | difficulty features | handling |
| 2. Baseline predictors | Logistic Regression, Decision Tree, SVM, Naive Bayes | Supervised learning, bias–variance, cross-validation, |
|   | “will this learner answer correctly?” | ROC/AUC |
| 3. Ensembles | Random Forest, XGBoost, stacking; hyperparameter | Bagging, boosting, regularisation, tuning |
|   | search |   |
| 4. Learner | K-Means / DBSCAN on behaviour vectors; PCA + t-SNE | Unsupervised learning, dimensionality reduction, cluster |
| segmentation | for visualising | validity |
| 5. Latent skill model | Bayesian Knowledge Tracing / Item Response Theory | Probabilistic models, MLE, EM, graphical model intuition |
| 6. Deep knowledge | LSTM/GRU, then a Transformer variant over question | Neural networks, backprop, sequence models, attention |
| tracing | sequences |   |
| 7. Language | Classify free-text doubts by concept; semantic similarity | NLP, tokenisation, TF-IDF embeddings |
| understanding | between a student's answer and the reference answer | transformers |
|   | using embeddings |   |
| 8. Adaptive tutor | Contextual bandit (ε-greedy, UCB, Thompson sampling), | Reinforcement learning, MDPs, exploration vs |
|   | then tabular Q-learning on a simulated learner | exploitation, reward design |
| 9. Anomaly detection | Isolation Forest / autoencoder to flag guessing, cheating, | Anomaly detection, autoencoders |
|   | or disengagement |   |
| 10. Explainability & | SHAP on the risk model, fairness audit across cohorts | Interpretable AI, responsible AI |
| ethics |   |   |
| 11. Deployment | FastAPI + Streamlit dashboard, model registry, drift | MLOps, model lifecycle |
|   | monitoring, retraining trigger |   |

## 3. Datasets


The project can use the following public datasets. They are free, large, sequential, and suitable for knowledge-tracing

and answer-correctness experiments:

- EdNet (KT1)

- ASSISTments 2009/2017

- RIIID Answer Correctness (Kaggle)

No web scraping is required when working with these public interaction logs.

## 4. Why It Defends Well in a Viva

Every module answers the question: “Why is this here?” with a real reason. Reinforcement learning is not bolted on — question selection genuinely is a sequential decision problem. The project can also be demonstrated live: a grader clicks through five questions and watches the mastery bars and question difficulty adapt.

## 5. End-to-End System Vision

Interaction Data Preprocessing & EDA Prediction Models Learner Segmentation Knowledge Tracing Deep Knowledge Tracing NLP Adaptive Question Selection Anomaly Detection Explainability & Fairness Deployment & Monitoring

Project Flagship: Mastery — Adaptive Learning Engine
