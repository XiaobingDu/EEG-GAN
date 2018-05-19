from torch.utils.data import Dataset
import numpy as np
import torch
import math
from utils import adjust_dynamic_range
import os


class MyDataset(Dataset):
    def __init__(self, dir_path='../MADSYN/data/eeg', num_files=200,
                 model_dataset_depth_offset=2,  # we start with 4x4 resolution instead of 1x1
                 model_initial_depth=0, alpha=1.0, range_in=(-1, 1), range_out=(-1, 1)):
        self.model_depth = model_initial_depth
        self.alpha = alpha
        self.range_out = range_out
        self.model_dataset_depth_offset = model_dataset_depth_offset
        self.range_in = range_in
        self.dir_path = dir_path
        self.all_files = sorted(list(map(lambda x: os.path.join(dir_path, x), os.listdir(dir_path))))[:num_files]
        num_files = len(self.all_files)
        self.seq_len = 256
        self.stride = 128
        sizes = []
        for i in range(num_files):
            with open(self.all_files[i]) as f:
                all_data_len = len(list(map(float, f.read().split())))
                sizes.append(max(int(np.ceil((all_data_len - self.seq_len + 1) / self.stride)), 0))
        self.sizes = sizes
        self.data_pointers = [(i, j) for i in range(num_files) for j in range(self.sizes[i])]
        num_points = [(self.sizes[i] - 1) * self.stride + self.seq_len for i in range(num_files)]
        self.datas = [np.zeros((1, num_points[i]), dtype=np.float32) for i in range(num_files)]
        for i in range(num_files):
            with open('{}_1.txt'.format(self.all_files[i][:-6])) as f:
                tmp = np.array(list(map(float, f.read().split())), dtype=np.float32)[:num_points[i]]
                self.datas[i][0, :] = ((tmp - tmp.min()) / (tmp.max() - tmp.min())) * 2.0 - 1.0
        self.max_dataset_depth = self.infer_max_dataset_depth(self.load_file(0))
        self.min_dataset_depth = self.model_dataset_depth_offset
        self.description = {
            'len': len(self),
            'shape': 'unknown',
            'depth_range': ('unknown', self.max_dataset_depth)
        }

    @property
    def data(self):
        raise AttributeError('FolderDataset.data property only accessible if preload is on.')

    @property
    def shape(self):
        return (len(self),) + self.load_file(0).shape

    def __len__(self):
        return len(self.data_pointers)

    def get_datapoint_version(self, datapoint, datapoint_depth, target_depth):
        if datapoint_depth == target_depth:
            return datapoint
        return self.create_datapoint_from_depth(datapoint, datapoint_depth, target_depth)

    def create_datapoint_from_depth(self, datapoint, datapoint_depth, target_depth):
        datapoint = datapoint.astype(np.float32)
        depthdiff = (datapoint_depth - target_depth)
        return datapoint[:, ::(2**depthdiff)]

    def load_file(self, item):
        i, k = self.data_pointers[item]
        res = self.datas[i][:, k * self.stride:k * self.stride + self.seq_len]
        return res

    @staticmethod
    def infer_max_dataset_depth(datapoint):
        return int(math.log(datapoint.shape[-1], 2))

    def __getitem__(self, item):
        datapoint = self.load_file(item)
        datapoint = self.get_datapoint_version(datapoint, self.max_dataset_depth,
                                               self.model_depth + self.model_dataset_depth_offset)
        datapoint = self.alpha_fade(datapoint)
        datapoint = adjust_dynamic_range(datapoint, self.range_in, self.range_out)
        return torch.from_numpy(datapoint.astype('float32'))

    def alpha_fade(self, datapoint):
        c, t = datapoint.shape
        t = datapoint.reshape(c, t // 2, 2).mean(axis=2).repeat(2, 1)
        datapoint = (datapoint + (t - datapoint) * (1 - self.alpha))
        return datapoint
