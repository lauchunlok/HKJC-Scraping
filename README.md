# HKJC-Scraping-

The project is aimed to help gamblers building up their own horse racing database for betting strategies. It consists of 4 scripts/notebooks, covering 4 different pages: 1. Race Result, 2. Horse Form Records, 3. Sectional Time & Position and 4. Race Card. With these pages information, you have more than enough data to do your own feature engineering. Happy yet cautious betting and win more!

Example page:
1. https://racing.hkjc.com/racing/information/english/Racing/LocalResults.aspx?RaceDate=2021/03/31
2. https://racing.hkjc.com/racing/information/English/Horse/Horse.aspx?HorseId=HK_2018_C453&Option=1
3. https://racing.hkjc.com/racing/information/english/Racing/DisplaySectionalTime.aspx?RaceDate=31/03/2021&RaceNo=1
4. https://racing.hkjc.com/racing/information/English/racing/RaceCard.aspx

### Race Result
In this page, the script will crawl the result table and prize money. You can change the number of years of crawling by specifying YEAR_START and YEAR_END on the top of the script. It takes around 10 mintues to complete one month. So on average, it takes an hour and a half to complete one year given that less/no horse racing in July to Augest.

### Horse Form Records
In this page, the script will crawl on the horse appeared in the interested time horizon which we specified in Race Result. It aims to provide a full historical record of horses so that we can include Lag features, e.g. average position in last X races. It is a relatively fast process and takes one mintue for one horse on average.

### Sectional Time & Position
The script mainly captures the Margin Behind Leader and Sectional Time which is not captured by Race Result. It can provide more information on horses' running style and performance at different Metres. Again, it takes around 10 mintues to complete one month. So on average, it takes an hour and a half to complete one year given that less/no horse racing in July to Augest.

### Race Card
Race card complement the dataset that it offers "Int'l Rtg.", 'Rtg.', 'Rtg.+/-', 'Horse Wt. (Declaration)', 'Wt.+/- (vs Declaration)', 'Best Time', 'Age' and 'Priority', etc. These features are exclusively on Race Card. **Unfortunately, past Race Card are not accessible anymore. (If you can find ways to access past Race Card record, I would appreciate it very much if you could tell me.) **

### Tips for Scraping


### Tips for merge


### Analysis


### Closing Words


### TODO
