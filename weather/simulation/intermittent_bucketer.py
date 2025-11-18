# The IntermittentBucketer only pools data from the defined buckets with no further discriminating features;
# It should work well with data that is independent from business processes, but correlated with the day of the year.

# It also provides a scaling structure that splits data into separate calendar years, for obtainiing per-year statistics.

from ..constants import Constants
from ..weather.Bucketer import Bucketer


class IntermittentBucketer(Bucketer):
    def __init__(
        self,
        historical_start_date,
        historical_end_date,
        draw_period=7,
        bucket_definition=Constants.MONTHLY_BUCKET_DEFINITION,
    ):
        categories = 1
        super().__init__(
            historical_start_date, historical_end_date, categories, draw_period, bucket_definition
        )

    # All data pooled in the same category, indiscriminately:
    def assign_Category(self, date):
        return 0

    def tabulate_Date_Info(self, date):
        return [self.bucket_of(date)]

    def get_Scaling_Structure(self):
        scaling_structure = {
            category: {n: [] for n in range(0, len(self.bucket_Definition))}
            for category in range(
                self.historical_End_Date.year - self.historical_Start_Date.year + 1
            )
        }

        for category in self.bucket_Structure:
            for bucket in self.bucket_Structure[category]:
                for date in self.bucket_Structure[category][bucket]:
                    scaling_structure[date.year - self.historical_Start_Date.year][bucket].append(
                        date
                    )

        return scaling_structure
