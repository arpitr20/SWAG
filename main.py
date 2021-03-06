# -*- coding: utf-8 -*-
"""main_swag.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1XssSrrjszH_sBTQ5_szbQAqpDyNxZdQa
"""

# Commented out IPython magic to ensure Python compatibility.
# this mounts your Google Drive to the Colab VM.
from google.colab import drive
drive.mount('/content/drive', force_remount=True)

FOLDERNAME = 'acmlab/teamswag/incomeproject'
assert FOLDERNAME is not None, "[!] Enter the foldername."

import sys
sys.path.append('/content/drive/My Drive/{}'.format(FOLDERNAME))

# %cd /content/drive/My\ Drive/$FOLDERNAME/

# Commented out IPython magic to ensure Python compatibility.
# Importing the standard ML libraries
# %reload_ext autoreload
# %autoreload 2

import pandas as pd                     # to process our data
import matplotlib.pyplot as plt         # graphing
import numpy as np                      # matrices
import torch
import torchvision                      # for working with images
import random
from torchvision import transforms, utils, datasets
from torch.utils.data import Dataset
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data.sampler import SubsetRandomSampler
from torch.utils.data import DataLoader
from sklearn.model_selection import train_test_split

import os
from PIL import Image
from webmercator import *
from util import *

device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

"""# Data Pre-proccessing:"""

income_data = pd.read_csv("16zpallnoagi.csv")
income_data = income_data[['ZIPCODE', 'N1', 'A02650']]
income_data = income_data[(income_data['ZIPCODE'] > 90000) & (income_data['ZIPCODE'] < 93000)] # filter LA zips
print(income_data)

ziplatlon_data = pd.read_csv("ziplatlon.csv", sep=';')
ziplatlon_data = ziplatlon_data[['zip', 'latitude', 'longitude']]
ziplatlon_data = ziplatlon_data[(ziplatlon_data['zip'] > 90000) & (ziplatlon_data['zip'] < 93000)] #filter CA zips
print(ziplatlon_data)

combined_data = pd.merge(left=ziplatlon_data, right=income_data, left_on='zip', right_on='ZIPCODE', sort = 1)
combined_data = combined_data.drop(columns = 'ZIPCODE')
print(combined_data)

zoom = 14 #constant defining zoom

path = '/content/drive/My Drive/acmlab/teamswag/incomeproject/imagery'
# Store the image file names in a list as long as they are jpgs
train_images = [f for f in os.listdir(path) if os.path.splitext(f)[-1] == '.jpg']
print(train_images)

tiles_data = pd.DataFrame()
images = []
lats = []
longs = []
zip = []
longInc = 1.0/45
latInc = 0.8/44
averageincome = []
for image in train_images:    
    # get x/y coordinates from name
    parts = image.split('.')[0].split('_')
    if (int(parts[0]) == zoom):
        images.append(image)
        x1=int(parts[1])-2794
        y1=int(parts[2])-6528
        lats.append(34.3-(y1+1)*latInc)
        longs.append(-118.6+x1*longInc)
        zip.append(0)
        averageincome.append(0)

tiles_data['tile'] = images
tiles_data['latitude'] = lats
tiles_data['longitude'] = longs
tiles_data['zip'] = zip
tiles_data['avg income'] = averageincome
print(tiles_data)

def getDistance(lat1, long1, lat2, long2):
    return ((lat1-lat2)**2+(long1-long2)**2)**0.5

#Assign center of zip code to tile it's in.
print(combined_data)
print(tiles_data)
#assign zip code to tile that has center
for i, j in combined_data.iterrows():
    zip = int(j[0])
    latitude = j[1]
    longitude = j[2]
    tiles_data.loc[(tiles_data['latitude'] <= latitude) & (tiles_data['latitude'] + latInc > latitude) & (tiles_data['longitude'] <= longitude) & (tiles_data['longitude'] + longInc > longitude), 'zip'] = zip
print(tiles_data[tiles_data['zip'] != 0])

#assign closest zip code for each land tile
for a, b in tiles_data.iterrows():
    latTile = b[1]+latInc/2
    longTile = b[2]+longInc/2
    if (getElevation(latTile, longTile) != 0):
        minZip = combined_data.iat[0, 0]
        minLat = combined_data.iat[0, 1]
        minLong = combined_data.iat[0, 2]
        minDistance = getDistance(latTile, longTile, minLat, minLong)
        cont = 1
        for i, j in combined_data.iterrows():
            curZip = int(j[0])
            curZip_data = combined_data[(combined_data['zip'] == curZip)]
            curLat = curZip_data.iat[0, 1]
            curLong = curZip_data.iat[0, 2]
            curDistance = getDistance(latTile, longTile, curLat, curLong)
            if (curDistance < minDistance):
                minDistance = curDistance
                minZip = curZip
            
        tiles_data.loc[(tiles_data['latitude'] <= latTile) & (tiles_data['latitude'] + latInc > latTile) & (tiles_data['longitude'] <= longTile) & (tiles_data['longitude'] + longInc > longTile), 'zip'] = minZip
print(tiles_data[tiles_data['zip'] != 0])

#print (tiles_data)
#distribute population/income
for i, j in combined_data.iterrows():
    zip = int(j[0])
    avgIncome = j[4]/j[3]
    tiles_data.loc[tiles_data['zip'] == zip, 'avg income'] = avgIncome

tiles_data = tiles_data[tiles_data['avg income'] != 0]

print(tiles_data)

print(tiles_data['avg income'])

tiles_data.to_csv('tiles_data.csv',index=True)  # save to csv files to make our lives a lot easier

"""# Implementing CNN's:
Initialize training and testing dataset
"""

tiles_data = pd.read_csv("tiles_data.csv", sep=',')
tiles_data = tiles_data.drop(columns = 'Unnamed: 0')
print(tiles_data)

class CustomDataSet(Dataset):
    def __init__(self, main_dir, transform):
        self.main_dir = main_dir
        self.transform = transform
        self.all_imgs = self.get_images()
        self.all_labels = self.get_labels()

    def __getitem__(self, idx):
        img_loc = os.path.join(self.main_dir, self.all_imgs[idx])
        image = Image.open(img_loc).convert("RGB")
        tensor_image = self.transform(image)
        label = self.all_labels[idx]
        return tensor_image, label

    def __len__(self):
        return len(self.all_imgs)

    def get_labels(self):
        return tiles_data['avg income'].tolist()

    def get_images(self):
        return tiles_data['tile'].tolist()

def Random90Rotate(p):
    if ((random.random()) < p):
        return torchvision.transforms.RandomRotation([90, 91])
    else:
        return torchvision.transforms.RandomRotation([0, 1])

transform_aug = torchvision.transforms.Compose([
                              torchvision.transforms.RandomHorizontalFlip(p=0.5),
                              torchvision.transforms.RandomVerticalFlip(p=0.5),
                              #torchvision.transforms.RandomApply(torch.nn.ModuleList([torchvision.transforms.RandomRotation([90, 91])]), p=0.5),
                              torchvision.transforms.ToTensor()])
transform_none = torchvision.transforms.ToTensor()

img_folder_path = '/content/drive/My Drive/acmlab/teamswag/incomeproject/imagery' #You might have to change this.

length = tiles_data.shape[0]

dset1 = CustomDataSet(img_folder_path, transform = transform_aug)
#dset2 = CustomDataSet(img_folder_path, transform = transform_none)
"""
all_indices=[]
train_indices=[]
for i in range(0, length):
    all_indices.append(i)
train_indices=random.sample(all_indices, k=length - 100)
test_indices = all_indices
print(train_indices, test_indices)
for x in train_indices:
    test_indices.remove(x)
print(test_indices)
"""

train_indices=[]
#test_indices=[] we will train on all the data we can, now - to do the best on test as possible.
for i in range(0, length):
    train_indices.append(i)

train_sampler = SubsetRandomSampler(train_indices)
#test_sampler = SubsetRandomSampler(test_indices)
batch_size = 64
train_loader = torch.utils.data.DataLoader(dset1, batch_size=batch_size, sampler=train_sampler)
#test_loader = torch.utils.data.DataLoader(dset2, batch_size=batch_size, sampler=test_sampler)

"""i = 210
image, label = dset1[i]
image = np.moveaxis(image.numpy(), 0, -1)
image = (image * 255).astype(np.uint8) # to preview, needs to be ints
display(Image.fromarray(image).convert("RGB"))
"""

#INSERT CNN CLASS AND MODEL CODE HERE!!!!!

"""Check accuracy on test dataset:

totalError = 0
totalPercentError = 0
totalNums = 0
maxError = 0
maxPercentError = 0
minError = 10000
minPercentError = 1000
with torch.no_grad():
  for images, labels in test_loader:
    outputs = cnn_model(images.to(device=device))
    labels = labels.to(device=device)
    predicted = torch.max(outputs.data, dim=1)
    for i in range (0, labels.size(0)):
        error = abs(predicted[0][i].item() - labels[i].item())
        percentError = abs(100*(predicted[0][i].item() - labels[i].item())/labels[i].item())
        if error > maxError:
            maxError = error
            maxErrorActual = labels[i].item()
            maxErrorPredicted = predicted[0][i].item()
            
            maxImage = images[i] # image shape: [3, 256, 256]
            maxIndex = i

        if percentError > maxPercentError:
            maxPercentError = percentError
            maxPercentErrorActual = labels[i].item()
            maxPercentErrorPredicted = predicted[0][i].item()
        if error < minError:
            minError = error
            minErrorActual = labels[i].item()
            minErrorPredicted = predicted[0][i].item()
        if percentError < minPercentError:
            minPercentError = percentError
            minPercentErrorActual = labels[i].item()
            minPercentErrorPredicted = predicted[0][i].item()
        totalError += abs(predicted[0][i].item() - labels[i].item())
        totalPercentError += abs(100*(predicted[0][i].item() - labels[i].item())/labels[i].item())
    totalNums += labels.size(0)

print(f'Average absolute error of the network on the {totalNums} test images: {totalError/totalNums}')
print("Max error: ", maxError,". Actual, predicted values: ", maxErrorActual, maxErrorPredicted)
maxImage = np.moveaxis(maxImage.numpy(), 0, -1) # image shape: [256, 256, 3]
maxImage = (maxImage * 255).astype(np.uint8) # to preview, needs to be ints
display(Image.fromarray(maxImage).convert("RGB"))
print(maxIndex)
print("Min error: ", minError,". Actual, predicted values: ", minErrorActual, minErrorPredicted)
print(f'Average percent error of the network on the {totalNums} test images: {totalPercentError/totalNums}%')
print("Max percent error: ", maxPercentError,". Actual, predicted values: ", maxPercentErrorActual, maxPercentErrorPredicted)
print("Min percent error: ", minPercentError,". Actual, predicted values: ", minPercentErrorActual, minPercentErrorPredicted)
"""

def predict(path = None):
    img_loc = path
    image = Image.open(img_loc).convert("RGB")
    tensor_image = transform_none(image).unsqueeze(0)
    return cnn_model(tensor_image.to(device=device)).squeeze().item()
