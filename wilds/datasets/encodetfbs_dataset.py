import os, time
import torch
import pandas as pd
import numpy as np
from wilds.datasets.wilds_dataset import WILDSDataset
from wilds.common.grouper import CombinatorialGrouper
from wilds.common.metrics.all_metrics import Accuracy

all_chrom_names = ['chr1', 'chr2', 'chr3', 'chr4', 'chr5', 'chr6', 'chr7', 'chr8', 'chr9', 'chr10', 'chr11', 'chr12', 'chr13', 'chr14', 'chr15', 'chr16', 'chr17', 'chr18', 'chr19', 'chr20', 'chr21', 'chr22', 'chrX']

class EncodeTFBSDataset(WILDSDataset):
    """
    ENCODE-DREAM-wilds dataset of transcription factor binding sites. 
    This is a subset of the dataset from the ENCODE-DREAM in vivo Transcription Factor Binding Site Prediction Challenge. 
    
    Input (x):
        1000-base-pair regions of sequence with a quantified chromatin accessibility readout.

    Label (y):
        y is binary. It is 1 if the central 200bp region is bound by the transcription factor MAX, and 0 otherwise.

    Metadata:
        Each sequence is annotated with the celltype of origin (a string) and the chromosome of origin (a string).
    
    Website:
        https://www.synapse.org/#!Synapse:syn6131484
    """

    def __init__(self, root_dir='data', download=False, split_scheme='official'):
        itime = time.time()
        self._dataset_name = 'encode-tfbs'
        self._version = '1.0'
        self._download_url = 'https://worksheets.codalab.org/rest/bundles/0x8b3255e21e164cd98d3aeec09cd0bc26/contents/blob/'
        self._data_dir = self.initialize_data_dir(root_dir, download)
        self._y_size = 1
        self._n_classes = 2
        
        self._train_chroms = ['chr2', 'chr3', 'chr4', 'chr5', 'chr6', 'chr7', 'chr9', 'chr10', 'chr11', 'chr12', 'chr13', 'chr14', 'chr15', 'chr16', 'chr17', 'chr18', 'chr19', 'chr20', 'chr22', 'chrX']
        # self._train_chroms = ['chr2', 'chr9', 'chr11']
        self._test_chroms = ['chr1', 'chr8', 'chr21']
        self._transcription_factor = 'MAX'
        self._train_celltypes = ['H1-hESC', 'HCT116', 'HeLa-S3', 'HepG2', 'K562']
        self._val_celltype = ['A549']
        self._test_celltype = ['GM12878']
        self._all_chroms = self._train_chroms + self._test_chroms
        self._all_celltypes = self._train_celltypes + self._val_celltype + self._test_celltype
        
        self._metadata_map = {}
        self._metadata_map['chr'] = self._all_chroms
        self._metadata_map['celltype'] = self._all_celltypes
        
        # Get the splits
        if split_scheme=='official':
            split_scheme = 'standard'
        
        self._split_scheme = split_scheme
        self._split_dict = {
            'train': 0,
            'id_val': 1,
            'test': 2,
            'val': 3
        }
        self._split_names = {
            'train': 'Train',
            'id_val': 'Validation (ID)',
            'test': 'Test',
            'val': 'Validation (OOD)',
        }
        
        # Load sequence and DNase features
        sequence_filename = os.path.join(self._data_dir, 'sequence.npz')
        seq_arr = np.load(sequence_filename)
        self._seq_bp = {}
        for chrom in self._all_chroms: #seq_arr:
            self._seq_bp[chrom] = seq_arr[chrom]
            print(chrom, time.time() - itime)
        
        self._dnase_allcelltypes = {}
        for ct in self._all_celltypes:
            """
            dnase_filename = os.path.join(self._data_dir, '{}_dnase.npz'.format(ct))
            dnase_npz_contents = np.load(dnase_filename)
            self._dnase_allcelltypes[ct] = {}
            for chrom in self._all_chroms: #self._seq_bp:
                self._dnase_allcelltypes[ct][chrom] = dnase_npz_contents[chrom]
            """
            self._dnase_allcelltypes[ct] = 'DNASE.{}.fc.signal.bigwig'
            print(ct, time.time() - itime)
        
        # Read in metadata dataframe from training+validation data
        train_regions_labeled = pd.read_csv(os.path.join(self._data_dir, 'labels/{}.train.labels.tsv.gz'.format(self._transcription_factor)), sep='\t')
        val_regions_labeled = pd.read_csv(os.path.join(self._data_dir, 'labels/{}.val.labels.tsv.gz'.format(self._transcription_factor)), sep='\t')
        training_df = train_regions_labeled[np.isin(train_regions_labeled['chr'], self._train_chroms)]
        val_df = val_regions_labeled[np.isin(val_regions_labeled['chr'], self._test_chroms)]
        all_df = pd.concat([training_df, val_df])
        
        # Filter by start/stop coordinate if needed (TODO: remove for final version)
        """
        filter_msk = all_df['start'] >= 0
        filter_msk = all_df['start']%1000 == 0
        all_df = all_df[filter_msk]
        """
        
        pd_list = []
        for ct in self._all_celltypes:
            tc_chr = all_df[['chr', 'start', 'stop', ct]]
            tc_chr.columns = ['chr', 'start', 'stop', 'y']
            tc_chr.insert(len(tc_chr.columns), 'celltype', ct)
            pd_list.append(tc_chr)
        metadata_df = pd.concat(pd_list)
        
        # Get the y values, and remove ambiguous labels by default.
        y_array = metadata_df['y'].replace({'U': 0, 'B': 1, 'A': -1}).values
        non_ambig_mask = (y_array != -1)
        metadata_df['y'] = y_array
        self._metadata_df = metadata_df[non_ambig_mask]
        
        samp_ndces = []
        itime = time.time()
        for ct in self._all_celltypes:
            neg_msk = np.logical_and((self._metadata_df['celltype'] == ct), (self._metadata_df['y'] == 0))
            pos_msk = np.logical_and((self._metadata_df['celltype'] == ct), (self._metadata_df['y'] == 1))
            neg_ndces = np.where(neg_msk)[0]
            pos_ndces = np.where(pos_msk)[0]
            np.random.seed(42)
            samp_neg_ndces = np.random.choice(neg_ndces, size=len(pos_ndces), replace=False)
            samp_ndces.extend(samp_neg_ndces)
            samp_ndces.extend(pos_ndces)
            print(ct, time.time() - itime)
        self._metadata_df = self._metadata_df.iloc[samp_ndces, :]
        
        train_regions_mask = np.isin(self._metadata_df['chr'], self._train_chroms)
        val_regions_mask = np.isin(self._metadata_df['chr'], self._test_chroms)
        train_celltype_mask = np.isin(self._metadata_df['celltype'], self._train_celltypes)
        val_celltype_mask = np.isin(self._metadata_df['celltype'], self._val_celltype)
        test_celltype_mask = np.isin(self._metadata_df['celltype'], self._test_celltype)
        
        split_array = -1*np.ones(self._metadata_df.shape[0]).astype(int)
        split_array[np.logical_and(train_regions_mask, train_celltype_mask)] = self._split_dict['train']
        split_array[np.logical_and(val_regions_mask, test_celltype_mask)] = self._split_dict['test']
        # Validate using test chr, either using a designated validation cell line ('val') or a training cell line ('id_val')
        split_array[np.logical_and(val_regions_mask, val_celltype_mask)] = self._split_dict['val']
        split_array[np.logical_and(val_regions_mask, train_celltype_mask)] = self._split_dict['id_val']
        
        if self._split_scheme=='standard':
            self._metadata_df.insert(len(self._metadata_df.columns), 'split', split_array)
        else:
            raise ValueError(f'Split scheme {self._split_scheme} not recognized')
        
        self._metadata_df = self._metadata_df[self._metadata_df['split'] != -1]
        self._split_array = self._metadata_df['split'].values
        
        chr_ints = self._metadata_df['chr'].replace(dict( [(y, x) for x, y in enumerate(self._metadata_map['chr'])] )).values
        celltype_ints = self._metadata_df['celltype'].replace(dict( [(y, x) for x, y in enumerate(self._metadata_map['celltype'])] )).values
        self._y_array = torch.LongTensor(np.array(self._metadata_df['y']))
        
        self._metadata_array = torch.stack(
            (torch.LongTensor(chr_ints), 
             torch.LongTensor(celltype_ints), 
             self._y_array),
            dim=1)
        self._metadata_fields = ['chr', 'celltype', 'y']
        
        self._eval_grouper = CombinatorialGrouper(
            dataset=self,
            groupby_fields=['celltype'])
        
        self._metric = Accuracy()
        
        super().__init__(root_dir, download, split_scheme)

    def get_input(self, idx):
        """
        Returns x for a given idx.
        Computes this from: 
        (1) sequence features in self._seq_bp
        (2) DNase features in self._dnase_allcelltypes
        (3) Metadata for the index (location along the genome with 200bp window width)
        """
        this_metadata = self._metadata_df.iloc[idx, :]
        flank_size = 400
        interval_start = this_metadata['start'] - flank_size
        interval_end = this_metadata['stop'] + flank_size
        dnase_this = self._dnase_allcelltypes[this_metadata['celltype']][this_metadata['chr']][interval_start:interval_end]
        seq_this = self._seq_bp[this_metadata['chr']][interval_start:interval_end]
        return torch.tensor(np.column_stack([seq_this, dnase_this]))

    def eval(self, y_pred, y_true, metadata):
        return self.standard_group_eval(
            self._metric,
            self._eval_grouper,
            y_pred, y_true, metadata)