import argparse
import csv
import os

import pandas as pd
import numpy as np


"""
Subsample the Amazon dataset.

Usage:

    python dataset_preprocessing/amazon_yelp/subsample_amazon.py <path> <frac>
"""

NOT_IN_DATASET = -1


def main(dataset_path, frac=0.25):
    def output_dataset_sizes(split_df):
        print("-" * 50)
        print(f'Train size: {len(split_df[split_df["split"] == 0])}')
        print(f'Val size: {len(split_df[split_df["split"] == 1])}')
        print(f'Test size: {len(split_df[split_df["split"] == 2])}')
        print(
            f'Number of examples not included: {len(split_df[split_df["split"] == NOT_IN_DATASET])}'
        )
        print("-" * 50)
        print("\n")

    data_df = pd.read_csv(
        os.path.join(dataset_path, "reviews.csv"),
        dtype={
            "reviewerID": str,
            "asin": str,
            "reviewTime": str,
            "unixReviewTime": int,
            "reviewText": str,
            "summary": str,
            "verified": bool,
            "category": str,
            "reviewYear": int,
        },
        keep_default_na=False,
        na_values=[],
        quoting=csv.QUOTE_NONNUMERIC,
    )

    user_csv_path = os.path.join(dataset_path, "splits", "user.csv")
    split_df = pd.read_csv(user_csv_path)
    output_dataset_sizes(split_df)

    train_data_df = data_df[split_df["split"] == 0]
    train_reviewer_ids = train_data_df.reviewerID.unique()
    print(f"Number of unique reviewers in train set: {len(train_reviewer_ids)}")

    blackout_indices = []
    for i, reviewer_id in enumerate(train_reviewer_ids):
        reviews = train_data_df[train_data_df["reviewerID"] == reviewer_id]

        # Randomly sample (1 - frac) x number of reviews this particular user has.
        # Add to blackout_indices to blackout later, so frac x number of reviews remain.
        blackout_count = int((1 - frac) * len(reviews))
        blackout_indices.extend(
            np.random.choice(reviews.index, blackout_count, replace=False)
        )

    # Mark all the corresponding reviews of blackout_indices as -1
    split_df.loc[blackout_indices, "split"] = NOT_IN_DATASET
    output_dataset_sizes(split_df)

    # Write out the new splits to user.csv
    split_df.to_csv(user_csv_path, index=False)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Subsample the Amazon dataset.")
    parser.add_argument(
        "path",
        type=str,
        help="Path to the Amazon dataset",
    )
    parser.add_argument(
        "frac",
        type=float,
        help="Subsample fraction",
    )

    args = parser.parse_args()
    main(args.path, args.frac)
